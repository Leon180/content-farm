"""Telegram approval domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApprovalResult(BaseModel):
    """Result of a Telegram approval checkpoint."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    approved: bool = False
    reply_text: str = ""
    edited_script: Any = None
