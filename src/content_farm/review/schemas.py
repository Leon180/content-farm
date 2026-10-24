"""JSON Schemas each reviewer's output must match (passed to ``claude -p --json-schema`` and
checked again here). Every issue must point at something verifiable: sentence ids, a time, an
asset, or a title / thumbnail field, plus a quote (``evidence``) from the material.
"""

from __future__ import annotations

from typing import Any

from content_farm.review.config import REWORK_STEPS

_STR = {"type": "string"}
_SCORE = {"type": "number", "minimum": 0, "maximum": 10}

ISSUE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ref", "category", "severity", "problem", "fix", "evidence", "caused_by"],
    "properties": {
        "ref": {
            "type": "object",
            "additionalProperties": False,
            "required": ["target"],
            "properties": {
                "target": {"enum": ["topic", "article", "script", "title", "thumbnail", "description",
                                    "media", "video", "audio"]},
                "sentence_ids": {"type": "array", "items": _STR},
                "scope": {"enum": ["sentences", "global"], "description": "global = a whole-script problem that "
                                                                          "cannot be narrowed to sentences"},
                "why_global": {"type": ["string", "null"], "description": "required when scope is global"},
                "t": {"type": ["string", "null"], "description": "m:ss in the video, when target is video/audio"},
                "item": {"type": ["string", "null"], "description": "candidate id, title id, thumbnail variant, "
                                                                  "asset/slide id or source id"},
            },
        },
        "category": {"enum": ["fact", "content", "structure", "visual", "audio", "pronunciation",
                              "title", "thumbnail", "compliance"]},
        "severity": {"enum": ["high", "med", "low"]},
        "problem": _STR,
        "fix": _STR,
        "evidence": {"type": "string", "description": "verbatim quote of the material the issue is about"},
        "caused_by": {"enum": list(REWORK_STEPS)},
        "claim_change": {"type": "boolean", "description": "true when the fix changes a chapter's argument"},
        "affected_slides": {"type": "array", "items": _STR, "description": "with claim_change: the slide ids "
                                                                         "(at most 3) whose argument changes"},
    },
}
_ISSUES = {"type": "array", "items": ISSUE}


def _obj(required: list[str], **props: Any) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": props}


# Quality v5: what the reviewer saw (a verbatim quote and a plain description, no judgement and no number) is kept apart
# from the scores and the fix list, so a score can later be compared with the observations that were supposed to justify it.
OBSERVATIONS = {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["quote", "observed"],
    "properties": {"quote": {"type": "string", "description": "verbatim quote of the material"},
                   "observed": {"type": "string", "description": "what is there, said plainly: no 'good/bad', no score"},
                   "sentence_ids": {"type": "array", "items": _STR}}}}

PRO = _obj(["role", "score", "rubric", "issues", "verdict"], observations=OBSERVATIONS,
           role=_STR, score=_SCORE,
           rubric={"type": "object", "additionalProperties": _SCORE}, issues=_ISSUES, verdict=_STR)

TOPIC_VIEWER = _obj(["persona", "picks", "overall"], persona=_STR, overall=_STR,
                    picks={"type": "array", "items": _obj(["candidate_id", "click", "why"],
                                                          candidate_id=_STR, click=_SCORE, why=_STR)})

TOPIC_PRO = _obj(["role", "scores", "verdict"], role=_STR, verdict=_STR,
                 scores={"type": "array", "items": _obj(
                     ["candidate_id", "score", "why", "veto"], candidate_id=_STR, score=_SCORE, why=_STR,
                     veto={"type": "boolean", "description": "duplicate, off-channel, unsourced or advice"},
                     duplicate_of={"type": ["string", "null"]})})

_CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1,
               "description": "how sure you are the claim is wrong/unsourced (0–1); < 0.5 is recorded, not fixed"}
CLAIM = _obj(["claim", "status", "evidence", "note"],   # confidence optional: missing = certain (confidence.py)
             confidence=_CONFIDENCE,
             claim=_STR, status={"enum": ["ok", "wrong", "unsourced", "unverifiable", "analysis"],
                                 "description": "analysis = the channel's own calculation/judgement, framed as such "
                                                "in the text, with math/logic you verified; framed as fact → unsourced"},
             evidence={"type": "string", "description": "verbatim quote of the claim in the material"},
             sentence_ids={"type": "array", "items": _STR}, source_id={"type": ["string", "null"]},
             source_quote={"type": ["string", "null"], "description": "what the source actually says"},
             note=_STR)
FACT = _obj(["role", "claims", "issues", "verdict"], role=_STR, verdict=_STR, issues=_ISSUES,
            claims={"type": "array", "items": CLAIM})

SCRIPT_VIEWER = _obj(
    ["persona", "segments", "left_at_sentence", "finish", "top_fixes", "overall"],
    persona=_STR, overall=_STR, finish={"type": "boolean"},
    left_at_sentence={"type": ["string", "null"], "description": "sentence id where you would leave, or null"},
    segments={"type": "array", "items": _obj(["slide_id", "engagement", "decision", "why"],
                                             slide_id=_STR, engagement=_SCORE, decision={"enum": ["stay", "leave"]},
                                             why=_STR, confusing={"type": "array", "items": _STR})},
    top_fixes=_ISSUES)

HOMEPAGE = {"type": "array", "items": _obj(["feed", "noticed", "picked", "why"], feed=_STR,
                                          noticed={"type": "array", "items": {"type": "integer"}},
                                          picked={"type": "integer"}, why=_STR)}

TITLE_VIEWER = _obj(
    ["persona", "homepage", "titles", "thumbnails", "top_fixes", "overall"],
    persona=_STR, overall=_STR, homepage=HOMEPAGE, top_fixes=_ISSUES,
    titles={"type": "array", "items": _obj(["title_id", "click"], title_id=_STR, click=_SCORE, why=_STR)},
    thumbnails={"type": "object", "additionalProperties": _SCORE})

PRODUCER_TITLE = _obj(
    ["role", "checks", "issues", "verdict"], role=_STR, verdict=_STR, issues=_ISSUES,
    checks={"type": "array", "items": _obj(["item", "exaggerated", "consistent", "why"],
                                          item=_STR, exaggerated={"type": "boolean"},
                                          consistent={"type": "boolean"}, why=_STR)})

DESIGNER = _obj(["role", "score", "rubric", "variants", "issues", "verdict"], role=_STR, score=_SCORE,
                rubric={"type": "object", "additionalProperties": _SCORE}, issues=_ISSUES, verdict=_STR,
                variants={"type": "object", "additionalProperties": _SCORE})

COMPLIANCE = _obj(
    ["role", "assets", "issues", "verdict"], role=_STR, verdict=_STR, issues=_ISSUES,
    assets={"type": "array", "items": _obj(["asset", "logo", "real_person", "official_character", "license_ok",
                                            "note"],
                                           asset=_STR, logo={"type": "boolean"}, real_person={"type": "boolean"},
                                           official_character={"type": "boolean"}, license_ok={"type": "boolean"},
                                           note=_STR)})

FINAL_VIEWER = _obj(
    ["persona", "segments", "left_at", "finish", "subscribe", "thumbnail_matches", "top_fixes", "overall"],
    persona=_STR, overall=_STR, finish={"type": "boolean"}, subscribe={"type": "boolean"},
    left_at={"type": ["string", "null"]}, thumbnail_matches={"type": "boolean"},
    pronunciation={"type": "array", "items": _STR},
    segments={"type": "array", "items": _obj(["t", "engagement", "decision", "why"], t=_STR, engagement=_SCORE,
                                             decision={"enum": ["stay", "leave"]}, why=_STR)},
    top_fixes=_ISSUES)

AGGREGATE = _obj(["fixes"], fixes={"type": "array", "items": _obj(
    ["problem", "fix", "caused_by", "sentence_ids", "votes", "category"],
    problem=_STR, fix=_STR, caused_by={"enum": list(REWORK_STEPS)}, category=_STR,
    sentence_ids={"type": "array", "items": _STR}, votes={"type": "integer"},
    members={"type": "array", "items": {"type": "integer"}})})

# (stage, role kind) → schema. Stages not listed for a kind fall back to the "*" entry.
SCHEMAS: dict[tuple[str, str], dict[str, Any]] = {
    ("topic", "viewer"): TOPIC_VIEWER, ("topic", "pro"): TOPIC_PRO, ("topic", "producer"): TOPIC_PRO,
    ("shorts_topic", "viewer"): TOPIC_VIEWER,
    ("script_structure", "viewer"): SCRIPT_VIEWER, ("shorts_script", "viewer"): SCRIPT_VIEWER,
    ("title_thumb", "viewer"): TITLE_VIEWER, ("shorts_title", "viewer"): TITLE_VIEWER,
    ("title_thumb", "producer"): PRODUCER_TITLE, ("title_thumb", "designer"): DESIGNER,
    ("final", "viewer"): FINAL_VIEWER, ("shorts_final", "viewer"): FINAL_VIEWER,
    ("*", "fact"): FACT, ("*", "pro"): PRO, ("*", "compliance"): COMPLIANCE,
}


def schema_for(stage: str, kind: str) -> dict[str, Any]:
    found = SCHEMAS.get((stage, kind)) or SCHEMAS.get(("*", kind))
    if found is None:
        raise ValueError(f"no output schema for a {kind} in stage {stage}")
    return found


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float),
          "null": type(None)}


def _type_ok(value: Any, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Errors of ``value`` against the JSON Schema subset used above (no jsonschema dependency)."""
    errors: list[str] = []
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_type_ok(value, k) for k in kinds):
            return [f"{path}: expected {'|'.join(kinds)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > {schema['maximum']}")
    if isinstance(value, dict):
        errors += _validate_object(value, schema, path)
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: {len(value)} items > {schema['maxItems']}")
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: {len(value)} items < {schema['minItems']}")
    if isinstance(value, list) and "items" in schema:
        for n, item in enumerate(value):
            errors += validate(item, schema["items"], f"{path}[{n}]")
    return errors


def _validate_object(value: dict, schema: dict[str, Any], path: str) -> list[str]:
    errors = [f"{path}: missing {key!r}" for key in schema.get("required", []) if key not in value]
    props = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in props:
            errors += validate(item, props[key], f"{path}.{key}")
        elif extra is False:
            errors.append(f"{path}: unexpected {key!r}")
        elif isinstance(extra, dict):
            errors += validate(item, extra, f"{path}.{key}")
    return errors
