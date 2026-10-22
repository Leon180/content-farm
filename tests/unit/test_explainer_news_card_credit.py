"""A title card that names a publisher and shows its headline is credited (cf-cost-accept, s02a)."""

from __future__ import annotations

from types import SimpleNamespace

from content_farm.explainer.media import _news_card_credit
from content_farm.explainer.media_run import credits_text


def _ctx(source) -> SimpleNamespace:
    return SimpleNamespace(deck=SimpleNamespace(source_by_id=lambda sid: source))


def _job() -> SimpleNamespace:
    return SimpleNamespace(slide=SimpleNamespace(id="s02a"), index=4)


SOURCE = SimpleNamespace(id="guardian-2022", publisher="The Guardian", headline="Japan's 'killing stone' splits",
                         title="t", published="2022-03-07", url="https://www.theguardian.com/x")


def test_the_card_credit_names_publisher_headline_date_and_url() -> None:
    credit = _news_card_credit(_ctx(SOURCE), _job(), "guardian-2022")
    assert credit["kind"] == "news_card" and credit["slide_id"] == "s02a"
    assert credit["publisher"] == "The Guardian" and credit["source_url"].endswith("/x") and credit["license"]


def test_no_source_id_no_credit() -> None:
    assert _news_card_credit(_ctx(SOURCE), _job(), "") is None


def test_the_description_lists_each_cited_report_once() -> None:
    credit = _news_card_credit(_ctx(SOURCE), _job(), "guardian-2022")
    text = credits_text([credit, {**credit, "slide_id": "s02b"}])
    assert text.count("The Guardian") == 1 and "Japan's 'killing stone' splits" in text and "2022-03-07" in text
