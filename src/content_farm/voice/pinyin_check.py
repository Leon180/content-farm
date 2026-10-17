"""Pinyin-level misread check (Leon 2026-10-17, decision 4e229eabdba5).

Whisper writes what it hears with *some* characters; a homophone (扣窩絲 for 扣窩斯) is not a
misread. So the narration and the transcript are both turned into pinyin and compared without
tones (``pinyin_cer``); same syllable with another tone is listed separately (``tone_errors``).
The character CER stays in speech_check.json as a reference column.

pypinyin is installed only in the local TTS venv, so the conversion runs there
(``scripts/pinyin_worker.py``); this module only compares.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from pathlib import Path

from content_farm.voice.speech_check import normalize

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER = REPO_ROOT / "scripts" / "pinyin_worker.py"
_TONE = re.compile(r"(\d)$")


def tts_python(env_file: Path | None = None) -> str | None:
    value = os.environ.get("CF_LOCAL_TTS_PYTHON")
    if not value and env_file and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CF_LOCAL_TTS_PYTHON="):
                value = line.split("=", 1)[1].strip().strip('"')
    path = Path(value).expanduser() if value else None
    return str(path) if path and path.is_file() else None


def to_pinyin(texts: list[str], python: str) -> list[list[str]]:
    result = subprocess.run([python, "-I", str(WORKER)], input=json.dumps(texts, ensure_ascii=False),
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"pinyin worker failed: {result.stderr[-400:]}")
    return json.loads(result.stdout)


def _toneless(syllable: str) -> str:
    return _TONE.sub("", syllable)


def _distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def compare(ref_text: str, hyp_text: str, ref_py: list[str], hyp_py: list[str]) -> dict:
    """``pinyin_cer`` on toneless syllables; ``tone_errors`` = same syllable, other tone."""
    ref_plain, hyp_plain = [_toneless(s) for s in ref_py], [_toneless(s) for s in hyp_py]
    cer = _distance(ref_plain, hyp_plain) / max(len(ref_plain), 1)
    tones = []
    matcher = difflib.SequenceMatcher(a=ref_plain, b=hyp_plain, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            i, j = block.a + k, block.b + k
            if ref_py[i] != hyp_py[j] and i < len(ref_text) and j < len(hyp_text):
                tones.append(f"{ref_text[i]}({ref_py[i]})→{hyp_text[j]}({hyp_py[j]})")
    return {"pinyin_cer": round(cer, 3), "tone_errors": tones[:12]}


def annotate(speech_check: Path, python: str) -> dict:
    """Add pinyin_cer / tone_errors to every record of speech_check.json (in place)."""
    checks = json.loads(speech_check.read_text(encoding="utf-8"))
    names = sorted(checks)
    refs = [normalize(checks[n].get("tts_text", "")) for n in names]
    hyps = [normalize(checks[n].get("hypothesis", "")) for n in names]
    pinyin = to_pinyin(refs + hyps, python)
    for k, name in enumerate(names):
        checks[name] = {**checks[name], **compare(refs[k], hyps[k], pinyin[k], pinyin[len(names) + k])}
    speech_check.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    return checks
