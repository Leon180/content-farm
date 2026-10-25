"""Per-channel YouTube refresh-token lookup.

One Google account owns several brand channels; each needs its own refresh
token. Env var naming: ``CF_YOUTUBE_REFRESH_TOKEN_<CHANNEL>`` (upper-case id),
falling back to the shared ``CF_YOUTUBE_REFRESH_TOKEN``.
"""

from __future__ import annotations

from collections.abc import Mapping

CHANNELS: tuple[str, ...] = ("chipcat", "cel", "yokai", "deepsea", "fable")

# Retired channel ids that publish under another channel's token.
CHANNEL_ALIASES: dict[str, str] = {"technews": "chipcat"}

_FALLBACK_ENV = "CF_YOUTUBE_REFRESH_TOKEN"


def normalize_channel(channel: str) -> str:
    """Lower-case the id and resolve aliases; reject unknown channels."""
    key = channel.strip().lower()
    key = CHANNEL_ALIASES.get(key, key)
    if key not in CHANNELS:
        raise ValueError(
            f"Unknown channel {channel!r}. Known: {', '.join(CHANNELS)} "
            f"(aliases: {', '.join(f'{a}->{b}' for a, b in CHANNEL_ALIASES.items())})"
        )
    return key


def token_env_name(channel: str) -> str:
    """Env var name that holds this channel's refresh token."""
    return f"{_FALLBACK_ENV}_{normalize_channel(channel).upper()}"


def resolve_token_source(channel: str, environ: Mapping[str, str]) -> str | None:
    """Return the env var name that supplies the token, or None if neither is set."""
    specific = token_env_name(channel)
    if environ.get(specific, "").strip():
        return specific
    if environ.get(_FALLBACK_ENV, "").strip():
        return _FALLBACK_ENV
    return None


def resolve_refresh_token(channel: str, environ: Mapping[str, str]) -> str:
    """Channel-specific token, else the shared one. Raises if neither is set."""
    source = resolve_token_source(channel, environ)
    if source is None:
        raise ValueError(
            f"No refresh token for channel {normalize_channel(channel)!r}: set "
            f"{token_env_name(channel)} (or {_FALLBACK_ENV}). "
            f"Run scripts/get_youtube_token.py --channel {normalize_channel(channel)}."
        )
    return environ[source].strip()
