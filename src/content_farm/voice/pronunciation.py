"""Shared pronunciation table (``channels/shared/pronunciation.yaml``).

Only the text sent to TTS changes; subtitles and slides keep the script's
wording. Merge order, later wins: ``shared`` → ``providers.<provider>`` →
``channels.<code>`` → the script's own ``pronunciation_map``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILE = REPO_ROOT / "channels" / "shared" / "pronunciation.yaml"


@dataclass(frozen=True)
class KeyTerm:
    display: str
    heard_as: tuple[str, ...] = ()


@dataclass(frozen=True)
class PronunciationTable:
    mapping: dict[str, str]
    key_terms: tuple[KeyTerm, ...]

    def spoken(self, display: str) -> str:
        """What the TTS is asked to say for ``display`` (itself when not remapped)."""
        return self.mapping.get(display, display)


def _str_map(value: object, where: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError(f"pronunciation {where} must map text to text")
    if any(not k.strip() or not v.strip() for k, v in value.items()):
        raise ValueError(f"pronunciation {where} has an empty entry")
    return dict(value)


def _key_terms(value: object) -> tuple[KeyTerm, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("pronunciation key_terms must be a list")
    terms = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("display"), str) or not item["display"].strip():
            raise ValueError(f"pronunciation key_terms entry needs a display string: {item!r}")
        heard = item.get("heard_as") or []
        if not isinstance(heard, list) or not all(isinstance(h, str) for h in heard):
            raise ValueError(f"pronunciation key_terms heard_as must be a list of strings: {item!r}")
        terms.append(KeyTerm(item["display"], tuple(heard)))
    return tuple(terms)


def _read(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"pronunciation table not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def load_table(path: Path, *, provider: str, channel: str = "") -> PronunciationTable:
    """The merged table for one provider and channel."""
    data = _read(path)
    providers = data.get("providers") or {}
    channels = data.get("channels") or {}
    mapping = {
        **_str_map(data.get("shared"), "shared"),
        **_str_map(providers.get(provider), f"providers.{provider}"),
        **_str_map(channels.get(channel), f"channels.{channel}"),
    }
    return PronunciationTable(mapping, _key_terms(data.get("key_terms")))


def table_fingerprint(path: Path, *, provider: str, channel: str = "") -> str:
    """Changes when the entries this provider/channel uses change (part of the voice identity)."""
    table = load_table(path, provider=provider, channel=channel)
    payload = repr((sorted(table.mapping.items()), table.key_terms))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def merged_map(table: PronunciationTable | None, script_map: dict[str, str] | None) -> dict[str, str]:
    """Table entries, then the script's own map (the script wins on the same key)."""
    return {**(table.mapping if table else {}), **(script_map or {})}
