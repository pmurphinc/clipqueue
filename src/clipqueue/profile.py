"""The content interview: questions, answer storage, and small helpers."""

from __future__ import annotations

import re
from typing import Any

from .config import data_dir, read_json, write_json

# key -> (label, YouTube category id)
CONTENT_TYPES: dict[str, tuple[str, str]] = {
    "gaming": ("Gaming highlights", "20"),
    "podcast": ("Podcast or talk clips", "22"),
    "sports": ("Sports", "17"),
    "comedy": ("Comedy or skits", "23"),
    "education": ("Tutorials or education", "27"),
    "cooking": ("Food or cooking", "26"),
    "music": ("Music", "10"),
    "vlog": ("Vlog or lifestyle", "22"),
    "other": ("Something else", "24"),
}

TONES: dict[str, str] = {
    "hype": "Hype",
    "funny": "Funny / meme",
    "chill": "Chill",
    "informative": "Informative",
    "dramatic": "Dramatic",
    "wholesome": "Wholesome",
}

TITLE_STYLES: dict[str, tuple[str, str]] = {
    "punchy": ("Short and punchy", "No way: 1v4 clutch"),
    "question": ("Question", "How is this even possible?"),
    "pov": ("POV", "POV: your teammate actually listened"),
    "descriptive": ("Descriptive", "1v4 clutch on Ascent | Valorant"),
    "caps": ("Big reaction", "UNREAL 1V4 CLUTCH"),
}

EMOJI_LEVELS: dict[str, str] = {"none": "None", "some": "A little", "lots": "Lots"}

DEFAULT_PROFILE: dict[str, Any] = {
    "content_type": "gaming",
    "specifics": "",
    "audience": "",
    "tones": ["hype"],
    "title_style": "punchy",
    "emoji": "some",
    "example_titles": "",
    "always_tags": "",
    "never_tags": "",
    "channel_name": "",
    "cta": "",
}


def load_profile() -> dict[str, Any]:
    return read_json(data_dir() / "profile.json", DEFAULT_PROFILE)


def save_profile(profile: dict[str, Any]) -> None:
    write_json(data_dir() / "profile.json", profile)


def profile_from_form(form: Any) -> dict[str, Any]:
    """Build a profile from a submitted interview form (a Starlette FormData)."""
    p = dict(DEFAULT_PROFILE)
    for key in DEFAULT_PROFILE:
        if key == "tones":
            continue
        val = form.get(key)
        if val is not None:
            p[key] = str(val).strip()
    tones = [t for t in form.getlist("tones") if t in TONES][:2]
    p["tones"] = tones or ["hype"]
    if p["content_type"] not in CONTENT_TYPES:
        p["content_type"] = "other"
    if p["title_style"] not in TITLE_STYLES:
        p["title_style"] = "punchy"
    if p["emoji"] not in EMOJI_LEVELS:
        p["emoji"] = "some"
    return p


def split_list(text: str) -> list[str]:
    """Split comma- or newline-separated text into clean items."""
    return [s.strip() for s in re.split(r"[,\n]+", text or "") if s.strip()]


def to_hashtag(text: str) -> str:
    """'Rocket League' -> '#rocketleague'. Returns '' if nothing usable is left."""
    core = re.sub(r"[^\w]", "", text.lstrip("#"), flags=re.UNICODE).lower()
    return f"#{core}" if core else ""


def hashtag_list(text: str) -> list[str]:
    tags = [to_hashtag(t) for t in re.split(r"[,\s]+", text or "")]
    return [t for t in tags if t]


def category_id(profile: dict[str, Any]) -> str:
    return CONTENT_TYPES.get(profile.get("content_type", "other"), CONTENT_TYPES["other"])[1]
