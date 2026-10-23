"""Review slimming (Leon 2026-10-24): script review judged once and applied once; fact checks count only claims with
confidence >= 0.5; every other panel is off; licences are a program rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production.channels import load_channel
from content_farm.review import license_rules
from content_farm.review.confidence import FACT_CONFIDENCE_MIN, demote_low_confidence, low_confidence_items
from content_farm.review.config import load_review
from content_farm.review.gate import panel_gate
from tests.unit.test_review_gate import FakePanel, _deck


@pytest.fixture(autouse=True)
def _v4_policy(monkeypatch):
    monkeypatch.delenv("CF_REVIEW_POLICY", raising=False)


# ── confidence ──────────────────────────────────────────────────────────────────────────────────

def _claim(status: str, confidence: float | None) -> dict:
    out = {"claim": "c", "status": status, "evidence": "e", "note": "n"}
    return out if confidence is None else {**out, "confidence": confidence}


def test_only_claims_at_or_above_half_confidence_stay_errors():
    out = {"claims": [_claim("wrong", 0.49), _claim("wrong", FACT_CONFIDENCE_MIN), _claim("unsourced", 0.9),
                      _claim("unsourced", None), _claim("ok", 0.1)]}
    after = demote_low_confidence(out)
    assert [c["status"] for c in after["claims"]] == ["low_confidence", "wrong", "unsourced", "unsourced", "ok"]
    assert after["claims"][0]["original_status"] == "wrong"
    assert len(low_confidence_items(after)) == 1
    assert out["claims"][0]["status"] == "wrong"          # the input is not mutated


def test_arbiter_rulings_are_demoted_too():
    after = demote_low_confidence({"rulings": [{"item": "a#0", "status": "wrong", "note": "", "confidence": 0.2}]})
    assert after["rulings"][0]["status"] == "low_confidence"


def test_a_low_confidence_claim_does_not_fail_the_fact_gate(tmp_path):
    from content_farm.review.verdicts import _fact_errors

    out = demote_low_confidence({"claims": [_claim("wrong", 0.3), _claim("wrong", 0.8)]})
    seat = type("S", (), {"output": out})()
    assert _fact_errors(seat) == 1


# ── shipped config ──────────────────────────────────────────────────────────────────────────────

def test_shipped_panels_keep_script_review_facts_and_topic_ranking_only():
    config = load_review("chipcat")
    off = {n for n, s in config.stages.items() if not s.enabled}
    assert off == {"title_thumb", "media", "final", "shorts_title", "shorts_final"}
    assert config.stages["script_structure"].max_rounds == 1 and config.policy.script_revise_once


def test_a_disabled_stage_opens_without_any_reviewer(tmp_path):
    called = []
    result = panel_gate(tmp_path, gate="final", stage_name="final", config=load_review("chipcat"), channel="chipcat",
                        channel_name="晶片貓", client=lambda call: called.append(call))
    assert result.status == "pass" and "關閉" in result.message and called == []


# ── script review: judged once, fixed once, never re-judged ─────────────────────────────────────

def _gate(run_dir: Path, panel: FakePanel):
    return panel_gate(run_dir, gate="deck", stage_name="script_structure", config=load_review("chipcat"),
                      channel="chipcat", channel_name="晶片貓", client=panel)


def _write_deck(run_dir: Path, narration: str) -> None:
    (run_dir / "deck.json").write_text(json.dumps(_deck(narration), ensure_ascii=False), encoding="utf-8")


def test_script_review_issues_one_automatic_fix_then_passes_without_a_second_judging(tmp_path):
    _write_deck(tmp_path, "開場第一句。開場第二句。")
    first = _gate(tmp_path, FakePanel(writer=9))                   # scores are fine, but the viewers left fixes
    assert first.status == "rework" and first.rework["restart"] == "deck" and first.rework["auto_fact_fix"]
    ledger = (tmp_path / "review" / "auto_fix.jsonl").read_text(encoding="utf-8")
    assert "fix_issued" in ledger
    _write_deck(tmp_path, "改過的開場？開場第二句。")
    panel = FakePanel(writer=2)                                    # a re-judging would fail the bar; it must not run
    second = _gate(tmp_path, panel)
    assert second.status == "pass" and panel.calls == []
    decision = json.loads((tmp_path / "review" / "deck.decision.json").read_text(encoding="utf-8"))
    assert decision["status"] == "approved"


def test_script_review_seats_are_audience_and_writers_only(tmp_path):
    _write_deck(tmp_path, "開場第一句。開場第二句。")
    panel = FakePanel(writer=9)
    _gate(tmp_path, panel)
    roles = {c.rid.rsplit("-", 1)[0] for c in panel.calls}
    assert roles == {"viewer", "writer_story", "writer_density"}


# ── licences as program rules ───────────────────────────────────────────────────────────────────

def _ai(**over) -> dict:
    return {"slide_id": "s1", "kind": "ai_image", "license": "AI-generated", "ai_generated": True, "ai_label": "AI 示意圖",
            "prompt": "flat editorial illustration, original generic scene", "model": "z-image-turbo", "seed": 42, **over}


def test_ai_images_with_badge_and_parameters_pass():
    assert license_rules.problems({"entries": [_ai(), {"slide_id": "s2", "kind": "parallax", "license": "own"}]}) == []


def test_unlisted_source_unlabelled_ai_and_missing_licence_fail():
    credits = {"entries": [_ai(ai_label=""), {"slide_id": "s2", "kind": "screengrab", "license": "x"},
                           {"slide_id": "s3", "kind": "stock", "license": ""}]}
    text = "；".join(license_rules.problems(credits))
    assert "白名單" in text and "screengrab" in text and "AI 示意圖" in text and "s3: 沒有授權" in text


def test_pending_licences_and_missing_credits_fail():
    assert license_rules.problems(None)
    assert any("未確定" in p for p in license_rules.problems({"entries": [], "pending": [{"slide_id": "s1"}]}))


def test_ent_is_retired_but_loadable():
    assert load_channel("ent").enabled is False
