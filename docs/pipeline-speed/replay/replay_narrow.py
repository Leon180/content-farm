"""Offline replay of item 2 on 九尾狐 review/ (no LLM, no spend). Before = old simple_scope on all issues,
after = narrow() + new simple_scope. python replay_narrow.py"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/lileon/project/content-farm/.claude/worktrees/cf-pipeline-speed-2/src")
from content_farm.review import routing  # noqa: E402
from content_farm.review.narrow import narrow  # noqa: E402
from content_farm.review.sentences import Sentence  # noqa: E402
from content_farm.review.article_diff import normalize  # noqa: E402

BASE = Path("/Users/lileon/project/content-farm/.claude/worktrees/cf-yokai-tempo/output/yokai-kyubi-v2/review")
SEQ = ["script/round-1", "script/round-2", "script/round-3", "script_structure/cycle-1/round-1",
       "script_structure/cycle-1/round-2", "script_structure/cycle-1/round-3", "script_structure/cycle-2/round-1",
       "script_structure/cycle-2/round-2"]
DECKS = [("deck-1", 0), ("deck-2", 1), ("deck-3", 3), ("deck-4", 4), ("deck-5", 6)]
LINE = re.compile(r"^\[([^\]]+)\] ~\d+:\d+ (.*)$")
IDS = re.compile(r"s\d+[a-z]?\.\d+")


def load_sentences(rel: str) -> list[Sentence]:
    out, section = [], ""
    for line in (BASE / rel / "script.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = LINE.match(line)
        if m:
            out.append(Sentence(m.group(1), m.group(1).rsplit(".", 1)[0], section, m.group(2), True))
    return out


def old_scope(issue, texts):
    """simple_scope as it was at 2fa8940 (whole-chapter expansion, no common-term cap)."""
    ref = issue.get("ref") or {}
    named = [str(i) for i in ref.get("sentence_ids") or []]
    terms = routing.terms_of(issue.get("evidence", ""))
    linked = [s.id for s in texts.sentences if s.id in named or any(t in s.text for t in terms)]
    if issue.get("claim_change"):
        sections = {s.section for s in texts.sentences if s.id in named}
        linked += [s.id for s in texts.sentences if s.section in sections and s.id not in linked]
    return set(linked)


def stats(issues, texts, scope_fn, changed):
    total = len(texts.sentences)
    ref = {str(i) for x in issues for i in (x.get("ref") or {}).get("sentence_ids") or []}
    scope = set()
    brief = set()
    for x in issues:
        s = scope_fn(x, texts)
        scope |= s
        brief |= s | set(IDS.findall(f"{x.get('problem', '')} {x.get('fix', '')}"))
    known = {s.id for s in texts.sentences}
    brief &= known
    cov = len(changed & scope) / len(changed) if changed else 1.0
    prec = len(changed & scope) / len(scope) if scope else 0.0
    return {"issues": len(issues), "ref": len(ref), "scope": len(scope), "brief": len(brief),
            "ref%": len(ref) / total, "scope%": len(scope) / total, "brief%": len(brief) / total,
            "cover": cov, "precision": prec}


rows = []
for name, idx in DECKS:
    before_rel, after_rel = SEQ[idx], SEQ[idx + 1]
    before, after = load_sentences(before_rel), load_sentences(after_rel)
    after_norm = {normalize(s.text) for s in after}
    changed = {s.id for s in before if normalize(s.text) not in after_norm}
    texts = routing.Texts(before)
    issues = json.loads((BASE / before_rel / "scorecard.json").read_text(encoding="utf-8"))["verdict"]["issues"]
    old = stats(issues, texts, old_scope, changed)
    import os
    kept, deferred, nstat = narrow(issues, before, per_seat=int(os.environ.get("PER_SEAT", 5)),
                                   hard=float(os.environ.get("HARD", 0.30)))
    new = stats(kept, texts, lambda x, t: set(routing.simple_scope(x, t).sentence_ids), changed)
    rows.append((name, len(before), len(changed), old, new, nstat))

fmt = "{:<7} {:>5} {:>7} | {:>5} {:>6} {:>6} {:>6} | {:>5} {:>6} {:>6} {:>6} | {:>6} {:>6} {:>6}"
print(fmt.format("run", "sent", "changed", "iss0", "ref0", "scope0", "brief0", "iss1", "ref1", "scope1", "brief1",
                 "cover0", "cover1", "prec1"))
for name, total, changed, o, n, ns in rows:
    print(fmt.format(name, total, changed, o["issues"], f"{o['ref%']:.0%}", f"{o['scope%']:.0%}", f"{o['brief%']:.0%}",
                     n["issues"], f"{n['ref%']:.0%}", f"{n['scope%']:.0%}", f"{n['brief%']:.0%}",
                     f"{o['cover']:.0%}", f"{n['cover']:.0%}", f"{n['precision']:.0%}"))
print("changed share:", ", ".join(f"{r[0]} {r[2] / r[1]:.0%}" for r in rows))
print("old precision:", ", ".join(f"{r[0]} {r[3]['precision']:.0%}" for r in rows))
print("narrow stats:", json.dumps([r[5] for r in rows], ensure_ascii=False))
