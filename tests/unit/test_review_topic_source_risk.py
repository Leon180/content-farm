"""Topic rubric: rumour-only / conflicting-quote / no-primary-source topics are marked down (cf-chipcat-run2)."""

from __future__ import annotations

from content_farm.review import producers, prompts
from content_farm.review.config import Role
from content_farm.review.materials import Materials


def _prompt(kind: str) -> str:
    role = Role(title="t", kind=kind, brief="b")
    return prompts.build("topic", role, Materials([], {}), channel="晶片貓")


def test_pro_and_producer_topic_seats_get_the_source_risk_rule() -> None:
    for kind in ("pro", "producer"):
        text = _prompt(kind)
        assert "傳聞" in text and "報價互相矛盾" in text and "一手來源" in text and "score ≤ 4" in text


def test_viewers_are_not_given_the_rule() -> None:
    assert "報價互相矛盾" not in _prompt("viewer")


def test_other_stages_are_unchanged() -> None:
    role = Role(title="t", kind="pro", brief="b")
    assert "報價互相矛盾" not in prompts.build("article", role, Materials([], {}), channel="c")


def test_topic_producer_brief_asks_for_a_primary_source_and_warns_off_rumour_topics() -> None:
    brief = producers.TASKS["topic"]
    assert "一手來源" in brief and "傳聞" in brief
