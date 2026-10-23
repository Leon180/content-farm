"""Claim audit for the entertainment channel: no sentence of fact without a source, no rumour told as fact.

The script writer attaches a :class:`Claim` to every factual sentence (hook / what / why / context beats; the
editor's-take beat is opinion and exempt). :func:`audit` then checks, deterministically, against the page the
pipeline actually read (``news_short.json`` → ``read.text_path``):

* ``NO_CLAIM``     — a sentence of fact with no claim (an unsourced assertion);
* ``BAD_SOURCE``   — the claim's source is not the page we read, or not a whitelisted outlet;
* ``NO_EVIDENCE``  — the claim's verbatim ``evidence`` quote does not occur in that page;
* ``UNATTRIBUTED`` — a reported (not confirmed) claim whose sentence does not read 「據{媒體}報導…」;
* ``NOT_CONFIRMED``— a claim marked confirmed whose evidence has no confirmation wording from the party itself,
  or whose sentence does not say who confirmed.

Leon's rule (2026-10-23): a failed fact audit is an error that goes through ``auto_fix`` — one automatic fix,
no re-check, then on: :func:`auto_fix` deletes what cannot be sourced and rewrites what is sourced but badly
attributed into the 「據…報導」 form. Both the errors and the fixes are written down by ``news.py audit``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_farm.retention.timing import split_sentences

if TYPE_CHECKING:
    from content_farm.production.news.script import NewsScript
    from content_farm.production.news.series import NewsSeries

FACT_BEATS = ("hook", "what", "why", "analogy")      # the "take" beat is the channel's own opinion
NO_CLAIM, BAD_SOURCE, NO_EVIDENCE, UNATTRIBUTED, NOT_CONFIRMED = (
    "NO_CLAIM", "BAD_SOURCE", "NO_EVIDENCE", "UNATTRIBUTED", "NOT_CONFIRMED")
DELETE_CODES = (NO_CLAIM, BAD_SOURCE, NO_EVIDENCE)
ATTRIBUTION = re.compile(r"據|根據|依據|依照")
REPORT_WORDS = re.compile(r"報導|報道|指出|透露|消息|引述|獨家|披露|說法")
CONFIRM_WORDS = re.compile(
    r"證實|宣布|宣佈|公布|公開|發文|聲明|回應|承認|確認|公告|官宣|表示|說明|親口|發表|親自|"
    r"confirm|announc|said|says|stated|statement|revealed|posted|"
    r"発表|認め|明かし|コメント|公式|明らか", re.I)


class Claim(BaseModel):
    """One factual sentence and where it comes from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sentence: str = Field(min_length=2)        # exactly one sentence of the beat's narration
    source: str                                # URL of the page that was read (a script source)
    status: Literal["confirmed", "reported"]   # confirmed = the party (本人／經紀公司／官方) said it; else a media report
    evidence: str = Field(min_length=6)        # verbatim passage from that page (original language)
    confirmed_by: str = ""                     # who confirmed it (required when status = confirmed)


@dataclass(frozen=True)
class Problem:
    beat: int            # index into script.beats
    sentence: str
    code: str
    detail: str

    def line(self) -> str:
        return f"beat {self.beat + 1}「{self.sentence[:24]}…」{self.code}：{self.detail}"


def squash(text: str) -> str:
    """NFKC, case-folded, without whitespace or punctuation — for 'is this quote on that page'."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if not (ch.isspace() or unicodedata.category(ch).startswith(("P", "S"))))


def _claim_for(beat, sentence: str) -> Claim | None:
    wanted = squash(sentence)
    return next((c for c in beat.claims if squash(c.sentence) == wanted), None)


def _read_urls(item: dict) -> set[str]:
    read = item.get("read") or {}
    return {u for u in (read.get("url"), read.get("final_url")) if u}


def _headlines(item: dict) -> set[str]:
    """The outlet's own headline of the story (feed title, page title): a claim may rest on it as well as on the page text."""
    read, cand = item.get("read") or {}, item.get("candidate") or {}
    return {squash(t) for t in (cand.get("title"), read.get("page_title")) if t}


def sentence_problem(beat_index: int, sentence: str, claim: Claim | None, *, read_urls: set[str],
                     page: str, series: NewsSeries, headlines: frozenset[str] | set[str] = frozenset()) -> Problem | None:
    def problem(code: str, detail: str) -> Problem:
        return Problem(beat_index, sentence, code, detail)

    if claim is None:
        return problem(NO_CLAIM, "這句事實沒有附出處（claims 裡找不到這句）")
    outlet = series.outlet(claim.source)
    if claim.source not in read_urls:
        return problem(BAD_SOURCE, f"出處 {claim.source} 不是這支片實際讀過的那一頁")
    if outlet is None:
        return problem(BAD_SOURCE, f"出處 {claim.source} 不在來源白名單")
    if squash(claim.evidence) not in page and squash(claim.evidence) not in headlines:
        return problem(NO_EVIDENCE, f"原文裡找不到這段佐證：{claim.evidence[:30]}")
    if claim.status == "confirmed":
        if not claim.confirmed_by or not CONFIRM_WORDS.search(claim.evidence):
            return problem(NOT_CONFIRMED, "標成已證實，但原文佐證沒有當事人／經紀公司／官方自己說的字樣，或沒寫是誰證實")
        if claim.confirmed_by not in sentence:
            return problem(NOT_CONFIRMED, f"已證實的句子要點名是誰證實（{claim.confirmed_by}）")
        return None
    named = any(name in sentence for name in outlet.names())
    if not (ATTRIBUTION.search(sentence) and REPORT_WORDS.search(sentence) and named):
        return problem(UNATTRIBUTED, f"傳聞／媒體報導要用「據{outlet.name}報導」的說法，不能直接當事實講")
    return None


def audit(script: NewsScript, item: dict, page_text: str, series: NewsSeries) -> list[Problem]:
    """Every problem of the script's factual sentences ([] = clean). ``page_text``: the cached original."""
    page = squash(page_text)
    urls, headlines = _read_urls(item), _headlines(item)
    problems = []
    for index, beat in enumerate(script.beats):
        if beat.kind not in FACT_BEATS:
            continue
        for sentence in split_sentences(beat.narration):
            found = sentence_problem(index, sentence, _claim_for(beat, sentence), read_urls=urls, page=page,
                                     series=series, headlines=headlines)
            if found:
                problems.append(found)
    return problems


def _attributed(sentence: str, publisher: str) -> str:
    body = re.sub(r"^(?:據|根據|依據|依照)[^，,。]{0,12}[，,]", "", sentence.strip())
    return f"據{publisher}報導，{body}"


@dataclass(frozen=True)
class Fix:
    beat: int
    code: str
    action: Literal["deleted", "rewritten"]
    before: str
    after: str


def _fallback(item: dict, series: NewsSeries, url: str) -> tuple[str, Claim] | None:
    """A beat whose every sentence had to go keeps one sentence that is certainly sourced: the headline."""
    cand = item.get("candidate") or {}
    outlet = series.outlet(url)
    title = (cand.get("title") or "").strip()
    if len(title) < 6 or outlet is None:
        return None
    sentence = f"據{outlet.name}報導，{title.rstrip('。')}。"
    return sentence, Claim(sentence=sentence, source=url, status="reported", evidence=title[:80])


def auto_fix(script: NewsScript, problems: list[Problem], item: dict, series: NewsSeries) -> tuple[NewsScript, list[Fix]]:
    """The one automatic fix: delete the unsourceable, rewrite the badly attributed. Returns a new script (inputs untouched)."""
    by_sentence: dict[tuple[int, str], Problem] = {(p.beat, squash(p.sentence)): p for p in problems}
    read_url = next(iter(sorted(_read_urls(item))), "")
    fixes: list[Fix] = []
    beats = []
    for index, beat in enumerate(script.beats):
        sentences, claims = [], []
        for sentence in split_sentences(beat.narration):
            hit = by_sentence.get((index, squash(sentence)))
            claim = _claim_for(beat, sentence)
            if hit is None:
                sentences.append(sentence)
                if claim:
                    claims.append(claim)
            elif hit.code in DELETE_CODES:
                fixes.append(Fix(index, hit.code, "deleted", sentence, ""))
            else:
                outlet = series.outlet(claim.source) if claim else None
                if outlet is None:
                    fixes.append(Fix(index, hit.code, "deleted", sentence, ""))
                    continue
                rewritten = _attributed(sentence, outlet.name)
                fixes.append(Fix(index, hit.code, "rewritten", sentence, rewritten))
                sentences.append(rewritten)
                claims.append(claim.model_copy(update={"sentence": rewritten, "status": "reported", "confirmed_by": ""}))
        if not sentences and beat.kind in FACT_BEATS:
            made = _fallback(item, series, read_url)
            if made:
                sentences, claims = [made[0]], [made[1]]
                fixes.append(Fix(index, "EMPTY_BEAT", "rewritten", beat.narration, made[0]))
        beats.append(beat.model_copy(update={"narration": "".join(sentences), "claims": tuple(claims)}))
    return script.model_copy(update={"beats": tuple(beats)}), fixes
