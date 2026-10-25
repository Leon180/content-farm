"""Tests for per-channel tokens, .env writer, quota ledger, pack parsing and upload runner."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from content_farm.youtube.channel_tokens import (
    normalize_channel,
    resolve_refresh_token,
    resolve_token_source,
    token_env_name,
)
from content_farm.youtube.env_file import EnvVarExistsError, set_env_var
from content_farm.youtube.pack import load_pack
from content_farm.youtube.pack_upload import RESULT_FILENAME, describe_item, run_upload
from content_farm.youtube.quota import QuotaLedger, upload_cost

# ---------- channel tokens ----------


def test_technews_is_its_own_channel_on_the_default_token() -> None:
    assert normalize_channel("technews") == "technews"
    assert token_env_name("technews") == "CF_YOUTUBE_REFRESH_TOKEN_TECHNEWS"
    assert resolve_token_source("technews", {"CF_YOUTUBE_REFRESH_TOKEN": "x"}) == "CF_YOUTUBE_REFRESH_TOKEN"


def test_specific_token_wins_over_shared() -> None:
    env = {"CF_YOUTUBE_REFRESH_TOKEN": "shared", "CF_YOUTUBE_REFRESH_TOKEN_CEL": "cel-tok"}
    assert resolve_refresh_token("cel", env) == "cel-tok"
    assert resolve_refresh_token("yokai", env) == "shared"


def test_missing_token_raises_with_hint() -> None:
    with pytest.raises(ValueError, match="get_youtube_token.py --channel fable"):
        resolve_refresh_token("fable", {})


def test_unknown_channel_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_channel("nope")


# ---------- env file ----------


def test_set_env_var_appends_and_preserves(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2", encoding="utf-8")
    env.chmod(0o600)
    assert set_env_var(env, "CF_YOUTUBE_REFRESH_TOKEN_CEL", "tok") == "appended"
    assert env.read_text(encoding="utf-8") == "A=1\nB=2\nCF_YOUTUBE_REFRESH_TOKEN_CEL=tok\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_set_env_var_refuses_existing_without_replace(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("X=old\nY=1\n", encoding="utf-8")
    with pytest.raises(EnvVarExistsError):
        set_env_var(env, "X", "new")
    assert env.read_text(encoding="utf-8") == "X=old\nY=1\n"
    assert set_env_var(env, "X", "new", replace=True) == "replaced"
    assert env.read_text(encoding="utf-8") == "X=new\nY=1\n"


def test_set_env_var_prefix_name_not_confused(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("CF_YOUTUBE_REFRESH_TOKEN=shared\n", encoding="utf-8")
    assert set_env_var(env, "CF_YOUTUBE_REFRESH_TOKEN_CEL", "t") == "appended"


def test_set_env_var_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        set_env_var(tmp_path / ".env", "bad name", "v")
    with pytest.raises(ValueError):
        set_env_var(tmp_path / ".env", "OK", "a\nb")


# ---------- quota ----------


def test_quota_ledger_persists_and_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    ledger = QuotaLedger.load(path, limit=3300)
    spent = ledger.spend("2026-10-24", 1651)
    assert ledger.used("2026-10-24") == 0
    assert spent.used("2026-10-24") == 1651
    assert QuotaLedger.load(path, limit=3300).remaining("2026-10-24") == 1649
    assert not spent.can_afford("2026-10-24", 1651)
    assert spent.can_afford("2026-10-25", 1651)


def test_upload_cost() -> None:
    assert upload_cost(has_thumbnail=False) == 1601
    assert upload_cost(has_thumbnail=True) == 1651


# ---------- pack fixtures ----------


def _metadata(channel_line: str, *, synthetic: str, thumb: str, desc: str = "說明") -> str:
    return (
        f"# {channel_line} — 標題 X\n\n"
        "| 項目 | 設定 |\n|---|---|\n"
        f"| 縮圖 | {thumb} |\n"
        "| 類別 | 科學與技術（Science & Technology） |\n"
        f"| 「經過修改或合成的內容」 | {synthetic} |\n\n"
        "## 標題（5/100 字）\n\n標題 X\n\n"
        f"## 說明欄（整段貼上）\n\n```text\n{desc}\n```\n\n"
        "## 標籤\n\nA, B，C\n\n## 注意事項\n- x\n"
    )


def _make_pack(root: Path) -> Path:
    rows = [
        ("tech-1", "科技新知", "晶片貓（chipcat，科技新知已併入）", "**否**", "Shorts 可略過", False),
        ("cel-1", "賽璐璐", "賽璐璐研究室（cel）", "**否**", "`thumbnail.jpg`", True),
        ("deep-1", "深潛", "深潛日誌（deepsea）", "**是（建議勾選）**", "`thumbnail.jpg`", True),
        ("fable-1", "寓言", "寓言學堂（暫名，Leon 尚未定名）", "**否**（見下）", "Shorts 略過", False),
        ("bad-1", "深潛", "深潛日誌（deepsea）", "**否**", "Shorts 略過", False),
    ]
    index = ["| # | 頻道 | 標題 | 長度 | 檔案 | 設定 | 注意 |", "|---|---|---|---|---|---|---|"]
    for n, (folder, ch, header, synthetic, thumb_cell, has_thumb) in enumerate(rows, 1):
        d = root / folder
        d.mkdir()
        (d / "video.mp4").write_bytes(b"v")
        if has_thumb:
            (d / "thumbnail.jpg").write_bytes(b"t")
        (d / "metadata.md").write_text(
            _metadata(header, synthetic=synthetic, thumb=thumb_cell), encoding="utf-8"
        )
        file_cell = f"{folder}/video.mp4（備註）"
        note = "**不建議上傳**" if folder == "bad-1" else "ok"
        index.append(f"| {n} | {ch} | t | 0:50 | {file_cell} | 私人 | {note} |")
    (root / "cel-1" / "pinned-comment.txt").write_text("c", encoding="utf-8")
    (root / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return root


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    return _make_pack(tmp_path)


# ---------- parsing ----------


def test_load_pack_parses_fields(pack: Path) -> None:
    items = load_pack(pack)
    assert [i.folder.name for i in items] == ["tech-1", "cel-1", "deep-1", "fable-1"]
    tech, cel, deep, fable = items
    assert tech.channel == "chipcat" and tech.is_short and tech.category_id == "28"
    assert tech.tags == ("A", "B", "C")
    assert cel.thumbnail_path == pack / "cel-1" / "thumbnail.jpg"
    assert cel.pinned_comment_path is not None
    assert deep.contains_synthetic_media is True
    assert fable.channel == "fable" and fable.contains_synthetic_media is False
    assert all(i.settings().privacy_status == "private" for i in items)


def test_only_and_limit(pack: Path) -> None:
    assert [i.folder.name for i in load_pack(pack, only="cel-1")] == ["cel-1"]
    assert len(load_pack(pack, limit=2)) == 2
    with pytest.raises(ValueError):
        load_pack(pack, only="bad-1")  # marked do-not-upload


def test_unlisted_folders_included_on_request(pack: Path) -> None:
    extra = pack / "extra-1"
    extra.mkdir()
    (extra / "video.mp4").write_bytes(b"v")
    (extra / "metadata.md").write_text(
        _metadata("深潛日誌（deepsea）", synthetic="**否**", thumb="Shorts"), encoding="utf-8"
    )
    names = [i.folder.name for i in load_pack(pack, include_unlisted=True)]
    assert "extra-1" in names and "bad-1" not in names
    assert "extra-1" not in [i.folder.name for i in load_pack(pack)]


def test_problems_flag_long_description_and_missing_flag(pack: Path) -> None:
    (pack / "tech-1" / "metadata.md").write_text(
        _metadata("晶片貓（chipcat）", synthetic="？", thumb="x", desc="字" * 1700),
        encoding="utf-8",
    )
    item = load_pack(pack, only="tech-1")[0]
    joined = " ".join(item.problems())
    assert "5000 bytes" in joined and "synthetic" in joined


def test_describe_item_shows_required_fields(pack: Path) -> None:
    item = load_pack(pack, only="deep-1")[0]
    out = describe_item(item, {"CF_YOUTUBE_REFRESH_TOKEN_DEEPSEA": "t"})
    for needle in ("deepsea", "標題 X", "containsSyntheticMedia: true", "privacyStatus: private",
                   "thumbnail.jpg", "CF_YOUTUBE_REFRESH_TOKEN_DEEPSEA", "A, B, C"):
        assert needle in out


# ---------- runner (mock provider, never touches the network) ----------


class FakeProvider:
    def __init__(self, thumb_fails: bool = False) -> None:
        self.inserts: list[dict] = []
        self.thumbs: list[str] = []
        self.thumb_fails = thumb_fails

    def get_authorized_channel(self) -> dict[str, str]:
        return {"id": "UC1", "title": "測試頻道"}

    async def upload_video(self, **kwargs) -> str:
        self.inserts.append(kwargs)
        return f"vid{len(self.inserts)}"

    async def set_thumbnail(self, *, video_id: str, thumbnail_path: Path) -> None:
        if self.thumb_fails:
            raise RuntimeError("quota")
        self.thumbs.append(video_id)


ENV = {"CF_YOUTUBE_REFRESH_TOKEN": "shared"}
CLOCK = lambda: datetime(2026, 10, 24, tzinfo=timezone.utc)  # noqa: E731


def _run(items, ledger, provider, **kw):
    factory = MagicMock(return_value=provider)
    outcomes = asyncio.run(
        run_upload(items, environ=ENV, ledger=ledger, provider_factory=factory,
                   log=lambda _m: None, clock=CLOCK, **kw)
    )
    return outcomes, factory


def test_upload_writes_result_and_private_settings(pack: Path, tmp_path: Path) -> None:
    items = load_pack(pack, only="deep-1")
    provider = FakeProvider()
    outcomes, factory = _run(items, QuotaLedger.load(tmp_path / "q.json"), provider)
    assert [o.status for o in outcomes] == ["uploaded"]
    factory.assert_called_once_with("deepsea", "shared")
    sent = provider.inserts[0]
    assert sent["settings"].privacy_status == "private"
    assert sent["settings"].contains_synthetic_media is True
    assert provider.thumbs == ["vid1"]
    result = json.loads((pack / "deep-1" / RESULT_FILENAME).read_text(encoding="utf-8"))
    assert result["videoId"] == "vid1"
    assert result["studioUrl"] == "https://studio.youtube.com/video/vid1/edit"
    assert result["channelTitle"] == "測試頻道" and result["thumbnailSet"] is True


def test_stops_when_quota_insufficient(pack: Path, tmp_path: Path) -> None:
    items = load_pack(pack)  # tech(1601) cel(1651) deep(1651) fable(1601)
    ledger = QuotaLedger.load(tmp_path / "q.json", limit=3300)
    provider = FakeProvider()
    outcomes, _ = _run(items, ledger, provider)
    assert [o.status for o in outcomes] == ["uploaded", "uploaded", "stopped-quota", "stopped-quota"]
    assert len(provider.inserts) == 2
    assert QuotaLedger.load(tmp_path / "q.json", limit=3300).days  # ledger persisted


def test_existing_result_skipped_unless_force(pack: Path, tmp_path: Path) -> None:
    items = load_pack(pack, only="tech-1")
    (pack / "tech-1" / RESULT_FILENAME).write_text("{}", encoding="utf-8")
    provider = FakeProvider()
    outcomes, _ = _run(items, QuotaLedger.load(tmp_path / "q.json"), provider)
    assert outcomes[0].status == "skipped-existing" and provider.inserts == []
    outcomes, _ = _run(items, QuotaLedger.load(tmp_path / "q.json"), provider, force=True)
    assert outcomes[0].status == "uploaded"


def test_item_with_problems_is_not_uploaded(pack: Path, tmp_path: Path) -> None:
    (pack / "cel-1" / "video.mp4").unlink()
    provider = FakeProvider()
    outcomes, _ = _run(load_pack(pack, only="cel-1"), QuotaLedger.load(tmp_path / "q.json"), provider)
    assert outcomes[0].status == "skipped-problems" and provider.inserts == []


def test_thumbnail_failure_keeps_video_id(pack: Path, tmp_path: Path) -> None:
    provider = FakeProvider(thumb_fails=True)
    outcomes, _ = _run(load_pack(pack, only="cel-1"), QuotaLedger.load(tmp_path / "q.json"), provider)
    assert outcomes[0].status == "uploaded"
    result = json.loads((pack / "cel-1" / RESULT_FILENAME).read_text(encoding="utf-8"))
    assert result["thumbnailSet"] is False and "thumbnailError" in result


def test_missing_token_fails_item_without_api_call(pack: Path, tmp_path: Path) -> None:
    provider = FakeProvider()
    factory = MagicMock(return_value=provider)
    outcomes = asyncio.run(
        run_upload(load_pack(pack, only="cel-1"), environ={}, ledger=QuotaLedger.load(tmp_path / "q.json"),
                   provider_factory=factory, log=lambda _m: None, clock=CLOCK)
    )
    assert outcomes[0].status == "failed" and factory.call_count == 0


# ---------- dry-run script never reaches the API ----------


def _load_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "upload_pack.py"
    spec = importlib.util.spec_from_file_location("upload_pack_script", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["upload_pack_script"] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_script_makes_no_provider_calls(pack: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "_make_provider", MagicMock(side_effect=AssertionError("API touched")))
    code = script.main(["--dry-run", "--pack-dir", str(pack), "--quota-file", str(tmp_path / "q.json")])
    assert code == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "cel-1" in out and "quota day" in out
    assert not (tmp_path / "q.json").exists()


# ---------- factory with channel ----------


def test_factory_picks_channel_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from content_farm.config import Settings
    from content_farm.youtube.factory import create_youtube_uploader

    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("CF_YOUTUBE_CLIENT_ID", "cid")
    monkeypatch.setenv("CF_YOUTUBE_CLIENT_SECRET", "cs")
    monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN", "shared")
    monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN_CHIPCAT", "chip")
    settings = Settings()  # type: ignore[call-arg]
    assert create_youtube_uploader(settings, channel="chipcat")._refresh_token == "chip"  # type: ignore[attr-defined]
    assert create_youtube_uploader(settings, channel="technews")._refresh_token == "shared"  # type: ignore[attr-defined]
    assert create_youtube_uploader(settings, channel="cel")._refresh_token == "shared"  # type: ignore[attr-defined]


def test_only_repeatable_keeps_index_order(pack: Path) -> None:
    got = [i.folder.name for i in load_pack(pack, only=["deep-1", "tech-1"])]
    assert got == ["tech-1", "deep-1"]
    with pytest.raises(ValueError):
        load_pack(pack, only=["tech-1", "nope"])


def test_dry_run_script_env_file_and_repeated_only(
    pack: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN_CEL", "x")  # registers cleanup of dotenv's leak
    monkeypatch.delenv("CF_YOUTUBE_REFRESH_TOKEN_CEL")
    env =tmp_path / "custom.env"
    env.write_text("CF_YOUTUBE_REFRESH_TOKEN_CEL=abc\n", encoding="utf-8")
    script = _load_script()
    code = script.main([
        "--dry-run", "--pack-dir", str(pack), "--quota-file", str(tmp_path / "q.json"),
        "--env-file", str(env), "--only", "cel-1", "--only", "tech-1",
    ])
    out = capsys.readouterr().out
    assert code == 0 and "(2 videos)" in out
    assert "token: CF_YOUTUBE_REFRESH_TOKEN_CEL" in out
    assert "abc" not in out


def test_angle_brackets_replaced_and_flagged(pack: Path) -> None:
    (pack / "tech-1" / "metadata.md").write_text(
        _metadata("晶片貓（chipcat）", synthetic="**否**", thumb="x", desc="V<C 且 A>B"),
        encoding="utf-8",
    )
    item = load_pack(pack, only="tech-1")[0]
    assert "<" not in item.description and ">" not in item.description
    assert item.description == "V＜C 且 A＞B"
    assert any("description" in n for n in item.notes)
    assert "SANITIZED" in describe_item(item, {})
    assert not any("<" in p for p in item.problems())


class FailingProvider(FakeProvider):
    async def upload_video(self, **kwargs) -> str:
        raise RuntimeError("invalidDescription")


def test_failed_insert_books_one_unit_only(pack: Path, tmp_path: Path) -> None:
    qfile = tmp_path / "q.json"
    outcomes, _ = _run(load_pack(pack, only="tech-1"), QuotaLedger.load(qfile), FailingProvider())
    assert outcomes[0].status == "failed"
    used = sum(QuotaLedger.load(qfile).days.values())
    assert used == 2  # channels.list (1) + failed call (1), not 1601
    assert not (pack / "tech-1" / RESULT_FILENAME).exists()


# ---------- read-back check ----------


def _video(item, **status_over):
    status = {"privacyStatus": "private", "madeForKids": False,
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False, **status_over}
    return {"snippet": {"title": item.title, "description": item.description,
                        "tags": list(item.tags), "categoryId": item.category_id,
                        "defaultLanguage": "zh-TW"}, "status": status}


def test_compare_video_flags_differences(pack: Path) -> None:
    from content_farm.youtube.verify import compare_video

    item = load_pack(pack, only="deep-1")[0]  # synthetic = True
    checks = {c.field: c for c in compare_video(item, _video(item))}
    assert not checks["containsSyntheticMedia"].ok
    assert all(c.ok for f, c in checks.items() if f != "containsSyntheticMedia")


def test_check_uploaded_script_reads_back(pack: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "check_uploaded_script", Path(__file__).resolve().parent.parent / "scripts" / "check_uploaded.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN", "shared")
    item = load_pack(pack, only="cel-1")[0]
    (pack / "cel-1" / RESULT_FILENAME).write_text('{"videoId": "v1"}', encoding="utf-8")
    fake = MagicMock()
    fake.get_videos.return_value = {"v1": _video(item, selfDeclaredMadeForKids=True)}
    code = module.main(["--pack-dir", str(pack), "--env-file", str(tmp_path / "none.env")],
                       provider_factory=lambda _t: fake)
    out = capsys.readouterr().out
    assert code == 1 and "DIFF selfDeclaredMadeForKids" in out and "1 video(s) checked" in out
    fake.get_videos.assert_called_once_with(["v1"])


# ---------- description fidelity / update_metadata ----------

REAL_PACK = Path("/Users/lileon/project/content-farm/output/upload-20261024")


def _raw_description_block(md: Path) -> str:
    """Independent, line-based extraction: lines between ```text and the next ``` after 說明欄."""
    lines = md.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 說明欄"))
    open_i = next(i for i in range(start, len(lines)) if lines[i].strip() == "```text")
    close_i = next(i for i in range(open_i + 1, len(lines)) if lines[i].strip() == "```")
    return "\n".join(lines[open_i + 1:close_i]).strip()


def test_description_block_taken_verbatim_with_hash_and_dash_lines(pack: Path) -> None:
    desc = "第一段\n\n章節：\n0:00 a\n\n— 署名\n\n#Shorts #標籤 #寓言"
    (pack / "tech-1" / "metadata.md").write_text(
        _metadata("晶片貓（chipcat）", synthetic="**否**", thumb="x", desc=desc), encoding="utf-8"
    )
    assert load_pack(pack, only="tech-1")[0].description == desc


@pytest.mark.skipif(not REAL_PACK.is_dir(), reason="real upload pack not on this machine")
def test_real_pack_descriptions_equal_block_length() -> None:
    from content_farm.youtube.pack import parse_metadata, sanitize_angle_brackets

    folders = sorted(p for p in REAL_PACK.iterdir() if (p / "metadata.md").is_file())
    assert len(folders) >= 12
    for folder in folders:
        want = sanitize_angle_brackets(_raw_description_block(folder / "metadata.md"))[0]
        got = parse_metadata(folder, listed_in_index=True).description
        assert got == want, f"{folder.name}: parsed {len(got)} != block {len(want)}"


class MetaProvider:
    def __init__(self) -> None:
        self.live = {"snippet": {"title": "舊", "description": "舊說明", "tags": ["x"],
                                 "categoryId": "22", "defaultLanguage": "zh-TW",
                                 "channelId": "UC1"}, "status": {}}
        self.updates: list[dict] = []

    def get_videos(self, ids):
        return {ids[0]: self.live}

    def update_snippet(self, video_id, changes):
        self.updates.append({"id": video_id, **changes})


def _load_update_script():
    spec = importlib.util.spec_from_file_location(
        "update_metadata_script", Path(__file__).resolve().parent.parent / "scripts" / "update_metadata.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_update_metadata_dry_run_then_apply(pack: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    module = _load_update_script()
    monkeypatch.setenv("CF_YOUTUBE_REFRESH_TOKEN", "shared")
    (pack / "cel-1" / RESULT_FILENAME).write_text('{"videoId": "v1"}', encoding="utf-8")
    provider = MetaProvider()
    base = ["--pack-dir", str(pack), "--env-file", str(tmp_path / "none.env"), "--only", "cel-1"]
    assert module.main(base, provider_factory=lambda _t: provider) == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "differs: title, description, tags, categoryId" in out
    assert "說明" in out and provider.updates == []
    assert module.main([*base, "--apply"], provider_factory=lambda _t: provider) == 0
    assert provider.updates and set(provider.updates[0]) == {"id", *module.FIELDS}


def test_update_snippet_preserves_other_fields() -> None:
    from content_farm.youtube.google_provider import GoogleProvider

    provider = GoogleProvider("c", "s", "r")
    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "v1", "snippet": {"title": "t", "defaultLanguage": "zh-TW",
                                           "defaultAudioLanguage": "zh-TW", "description": "d"}}]
    }
    provider._service = service
    written = provider.update_snippet("v1", {"description": "new"})
    body = service.videos.return_value.update.call_args.kwargs["body"]
    assert service.videos.return_value.update.call_args.kwargs["part"] == "snippet"
    assert body["snippet"] == written
    assert written["description"] == "new" and written["defaultAudioLanguage"] == "zh-TW"
