"""Read-back check: did the TTS say what the script says?

Each synthesized scene is transcribed with whisper (local worker, converted to
Traditional Chinese) and compared with the script's narration:

- CER: character edit distance / reference length, after normalising variant
  characters (臺/台, 裏/裡 …), dropping punctuation and spelling numbers the way
  they are read (7,722 → 七千七百二十二; 2024 年 → 二零二四年).
- key terms (``key_terms`` in the pronunciation table): every term in the
  narration must be heard — its display form or one of its ``heard_as``
  homophones must appear in the transcript.

The reference is the *display* narration, not the TTS text: pronunciation
substitutes are homophones (蘆葦 → 盧偉), so a correct reading transcribes back
to the original word.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from content_farm.voice.pronunciation import KeyTerm
from content_farm.voice.text_normalize import normalize_for_tts

# opencc s2t leaves these variants; whisper's output and the scripts must compare equal.
VARIANTS = str.maketrans("臺裏爲着綫於糰衆峯羣啓纔喫", "台裡為著線于團眾峰群啟才吃")
_DIGITS = "零一二三四五六七八九"
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)(%?)")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")


def _four_digits(value: int) -> str:
    """0 < value < 10000, read positionally (一千零五, 二十)."""
    out, zero = [], False
    for unit, place in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        digit = value // unit % 10
        if digit == 0:
            zero = bool(out)
            continue
        if zero:
            out.append("零")
            zero = False
        out.append(_DIGITS[digit] + place)
    text = "".join(out)
    return text[1:] if text.startswith("一十") else text


def number_to_zh(value: int) -> str:
    if value == 0:
        return "零"
    parts, groups = [], ((100_000_000, "億"), (10_000, "萬"), (1, ""))
    for unit, name in groups:
        chunk = value // unit % 10_000 if unit < 100_000_000 else value // unit
        if chunk:
            if parts and chunk < 1000:
                parts.append("零")
            parts.append(_four_digits(chunk) + name if chunk < 10_000 else number_to_zh(chunk) + name)
    return "".join(parts)


def _spell_number(match: re.Match) -> str:
    number, percent = match.group(1), match.group(2)
    whole, _, frac = number.partition(".")
    text = number_to_zh(int(whole)) + ("點" + "".join(_DIGITS[int(d)] for d in frac) if frac else "")
    return f"百分之{text}" if percent else text


def normalize(text: str) -> str:
    """Comparable form: Traditional variants unified, numbers spelled, only letters/digits kept."""
    text = unicodedata.normalize("NFKC", text).translate(VARIANTS).replace("想象", "想像").replace("×", "乘")
    text = normalize_for_tts(text)  # years digit by digit, as they are read
    text = _NUMBER.sub(_spell_number, _THOUSANDS.sub("", text))
    return "".join(c for c in text if unicodedata.category(c)[0] in "LN").lower()


Aliases = tuple[tuple[str, str], ...]


def build_aliases(terms: tuple[KeyTerm, ...], mapping: dict[str, str] | None = None) -> Aliases:
    """(heard form, display form) pairs, normalised, longest first. A correct reading may come
    back as a key term's ``heard_as`` homophone, or as the pronunciation table's spoken spelling
    (盧偉 for 蘆葦); both count as the display word. Single-character spellings are skipped:
    mapping 務 back to 霧 would corrupt every 任務."""
    pairs = {(normalize(heard), normalize(term.display)) for term in terms for heard in term.heard_as}
    pairs |= {(normalize(spoken), normalize(display)) for display, spoken in (mapping or {}).items()
              if len(normalize(spoken)) >= 2}
    return tuple(sorted(((h, d) for h, d in pairs if h and h != d), key=lambda p: -len(p[0])))


def canonical(hypothesis: str, aliases: Aliases = ()) -> str:
    text = normalize(hypothesis)
    for heard, display in aliases:
        text = text.replace(heard, display)
    return text


def cer(reference: str, hypothesis: str, aliases: Aliases = ()) -> float:
    ref, hyp = normalize(reference), canonical(hypothesis, aliases)
    row = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, hc in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (rc != hc))
    return row[len(hyp)] / max(len(ref), 1)


def missing_terms(reference: str, hypothesis: str, terms: tuple[KeyTerm, ...],
                  aliases: Aliases | None = None) -> tuple[str, ...]:
    """Key terms in the narration that the transcript does not contain as often (in any accepted form).

    Counted, not just present: a scene that says 鷹 three times and is heard saying it once has two
    misreadings (2026-10-24: one right 貓頭鷹 hid the wrong ones in the same scene)."""
    ref = normalize(reference)
    hyp = canonical(hypothesis, build_aliases(terms) if aliases is None else aliases)
    return tuple(term.display for term in terms
                 if normalize(term.display) in ref and ref.count(normalize(term.display)) > hyp.count(normalize(term.display)))


@dataclass(frozen=True)
class Attempt:
    seed: int | None
    cer: float
    missing: tuple[str, ...]
    hypothesis: str

    def passes(self, max_cer: float) -> bool:
        return self.cer <= max_cer and not self.missing

    def rank(self) -> tuple[int, float]:
        return (len(self.missing), self.cer)


@dataclass(frozen=True)
class SceneCheck:
    """All attempts for one scene; ``chosen`` is the take kept on disk."""
    attempts: tuple[Attempt, ...]
    chosen: int
    max_cer: float
    extra: dict = field(default_factory=dict)

    @property
    def best(self) -> Attempt:
        return self.attempts[self.chosen]

    @property
    def status(self) -> str:
        return "ok" if self.best.passes(self.max_cer) else "warn"

    def to_json(self) -> dict:
        best = self.best
        return {
            "status": self.status, "cer": round(best.cer, 3), "missing_terms": list(best.missing),
            "attempts": len(self.attempts), "regenerations": len(self.attempts) - 1, "seed": best.seed,
            "max_cer": self.max_cer, "hypothesis": best.hypothesis,
            "history": [{"seed": a.seed, "cer": round(a.cer, 3), "missing_terms": list(a.missing)}
                        for a in self.attempts],
            **self.extra,
        }


def evaluate(reference: str, hypothesis: str, terms: tuple[KeyTerm, ...], seed: int | None,
             aliases: Aliases | None = None) -> Attempt:
    aliases = build_aliases(terms) if aliases is None else aliases
    return Attempt(seed, cer(reference, hypothesis, aliases), missing_terms(reference, hypothesis, terms, aliases),
                   hypothesis)


def choose(attempts: tuple[Attempt, ...]) -> int:
    """Index of the best attempt: fewest missing key terms, then lowest CER, then earliest."""
    return min(range(len(attempts)), key=lambda i: (*attempts[i].rank(), i))
