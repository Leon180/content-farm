"""Tests for Telegram approval domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_farm.telegram.schemas import ApprovalResult


class TestApprovalResult:
    def test_defaults(self) -> None:
        r = ApprovalResult()
        assert r.approved is False
        assert r.reply_text == ""

    def test_approved(self) -> None:
        r = ApprovalResult(approved=True, reply_text="ok")
        assert r.approved is True
        assert r.reply_text == "ok"

    def test_frozen(self) -> None:
        r = ApprovalResult()
        with pytest.raises(ValidationError):
            r.approved = True  # type: ignore[misc]

    def test_frozen_reply_text(self) -> None:
        r = ApprovalResult(reply_text="ok")
        with pytest.raises(ValidationError):
            r.reply_text = "changed"  # type: ignore[misc]
