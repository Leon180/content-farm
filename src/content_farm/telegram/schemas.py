"""Telegram approval domain models."""

from __future__ import annotations

from pydantic import BaseModel


class ApprovalResult(BaseModel):
    """Result of a Telegram approval checkpoint."""

    model_config = {"frozen": True}

    approved: bool = False
    reply_text: str = ""
