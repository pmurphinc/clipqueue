"""Optional: ask a locally installed `claude` CLI for title suggestions.

This uses the person's own Claude subscription through the CLI they already
have. ClipQueue never sees or stores any Claude credentials. If anything goes
wrong, callers fall back to the offline generator.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from ..profile import CONTENT_TYPES, TITLE_STYLES, TONES, hashtag_list
from .offline import MAX_HASHTAGS, sanitize_title

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def cli_path() -> str | None:
    return shutil.which("claude")


def build_prompt(profile: dict[str, Any], clip: dict[str, Any], short: bool, n: int) -> str:
    ctype = CONTENT_TYPES.get(profile.get("content_type", "other"), CONTENT_TYPES["other"])[0]
    tones = ", ".join(TONES.get(t, t) for t in profile.get("tones", []))
    style = TITLE_STYLES.get(profile.get("title_style", "punchy"), ("",))[0]
    examples = "\n".join(f"- {t.strip()}" for t in (profile.get("example_titles") or "").splitlines() if t.strip())
    duration = f"{clip['duration']:.0f} seconds" if clip.get("duration") else "unknown length"
    return f"""You write YouTube titles for a creator. Reply with JSON only, no prose.

Creator profile:
- Content: {ctype}
- Games / show / topics: {profile.get('specifics') or 'not given'}
- Audience: {profile.get('audience') or 'not given'}
- Tone: {tones or 'not given'}
- Preferred title style: {style}
- Emoji: {profile.get('emoji', 'some')}
- Channel name: {profile.get('channel_name') or 'not given'}
- Call to action for descriptions: {profile.get('cta') or 'none'}
- Hashtags to always include: {profile.get('always_tags') or 'none'}
- Hashtags to never use: {profile.get('never_tags') or 'none'}
- Titles they like:
{examples or '- none given'}

Clip:
- File name: {clip.get('filename')}
- Folder: {clip.get('folder')}
- Length: {duration}{' (vertical, will be a YouTube Short)' if short else ''}
- Creator's note: {clip.get('note') or 'none'}

Write {n} different options. Titles: under 70 characters, no angle brackets, don't invent
specific facts the file name and note don't support. Hashtags: at most {MAX_HASHTAGS}, most
relevant first{', include #shorts' if short else ''}. Description: 1-3 short lines, then the call
to action if given. Do not put hashtags in the description.

JSON shape:
{{"options": [{{"title": "...", "description": "...", "hashtags": ["#..."]}}]}}"""


def _extract_json(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def suggest(profile: dict[str, Any], clip: dict[str, Any], short: bool = False, n: int = 3,
            timeout: int = 120) -> list[dict[str, Any]]:
    """Return suggestions, or raise RuntimeError with a short reason."""
    exe = cli_path()
    if not exe:
        raise RuntimeError("claude CLI not found")
    prompt = build_prompt(profile, clip, short, n)
    try:
        # The prompt goes in on stdin so Windows command-line quoting can't mangle it.
        proc = subprocess.run(
            [exe, "-p", "Follow the instructions above and reply with JSON only."],
            input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("claude CLI timed out") from e
    except OSError as e:
        raise RuntimeError(f"could not run claude CLI: {e}") from e
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr or "").strip().splitlines()
        raise RuntimeError(f"claude CLI error: {detail[0][:160] if detail else proc.returncode}")
    data = _extract_json(proc.stdout or "")
    if not data or not isinstance(data.get("options"), list):
        raise RuntimeError("claude CLI gave no usable answer")

    never = {t.lower() for t in hashtag_list(profile.get("never_tags", ""))}
    always = hashtag_list(profile.get("always_tags", ""))
    out = []
    for opt in data["options"][:n]:
        if not isinstance(opt, dict) or not opt.get("title"):
            continue
        tags = []
        for t in [*always, *hashtag_list(" ".join(map(str, opt.get("hashtags") or [])))]:
            if t.lower() not in never and t.lower() not in {x.lower() for x in tags}:
                tags.append(t)
        tags = tags[:MAX_HASHTAGS]
        desc = str(opt.get("description") or "").strip()
        out.append({
            "style": "ai",
            "title": sanitize_title(str(opt["title"])),
            "description": "\n\n".join(p for p in [desc, " ".join(tags)] if p),
            "hashtags": tags,
        })
    if not out:
        raise RuntimeError("claude CLI gave no usable answer")
    return out
