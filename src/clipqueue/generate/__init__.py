"""Suggestion entry point: AI if enabled and working, otherwise offline."""

from __future__ import annotations

from typing import Any

from . import claude_cli, offline


def suggest(profile: dict[str, Any], clip: dict[str, Any], settings: dict[str, Any],
            short: bool, use_ai: bool | None = None) -> tuple[list[dict[str, Any]], str]:
    """Return (options, note). The note explains which generator was used."""
    picks = settings.get("style_picks", {})
    base = offline.suggest(profile, clip, picks, short)
    want_ai = settings.get("ai_enabled") if use_ai is None else use_ai
    if not want_ai:
        return base, "offline"
    try:
        ai = claude_cli.suggest(profile, clip, short)
    except RuntimeError as e:
        return base, f"offline (AI unavailable: {e})"
    # Keyword tags still come from the offline generator.
    for opt in ai:
        opt["tags"] = base[0]["tags"]
    return ai, "claude"
