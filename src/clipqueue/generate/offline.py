"""Offline title, description and hashtag suggestions. No network, no AI.

The output is shaped by the interview answers:
  - title_style picks the template family
  - tones pick the hook words and emoji
  - specifics become the topic and topic hashtags
  - example titles set a target length
  - always/never hashtag lists are applied last
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from ..profile import TITLE_STYLES, hashtag_list, split_list, to_hashtag

TITLE_MAX = 100          # YouTube limit
MAX_HASHTAGS = 5         # YouTube shows the first 3 above the title
TAGS_MAX_CHARS = 450     # YouTube allows ~500 characters of tags in total

NOISE = {
    "clip", "clips", "video", "replay", "recording", "record", "final", "edit", "edited",
    "export", "exported", "copy", "vod", "obs", "medal", "shadowplay", "nvidia", "geforce",
    "xbox", "dvr", "capture", "captured", "untitled", "trim", "trimmed", "output", "raw",
    "fixed", "instant", "new", "highlight", "highlights", "short", "shorts", "img", "vid",
    "mov", "mp4", "screen", "screenrecording", "recorded",
}
SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
DATE_RE =re.compile(r"\d{4}[-_. ]?\d{2}[-_. ]?\d{2}")
TIME_RE = re.compile(r"\b\d{1,2}[-_.h]\d{2}([-_.m]\d{2})?s?\b")

HOOKS: dict[str, list[str]] = {
    "hype": ["No way", "Unreal", "Absolutely insane", "Clean", "Clutch"],
    "funny": ["I can't stop laughing", "Why did this happen", "This went so wrong", "Bro really tried it"],
    "chill": ["A clean one", "Smooth", "Pretty satisfying", "Just vibes"],
    "informative": ["Quick tip", "How this works", "Watch this", "Remember this"],
    "dramatic": ["Nobody saw this coming", "It all went wrong", "This was way too close", "The turning point"],
    "wholesome": ["This made my day", "Love this", "Wholesome moment", "Good vibes only"],
}
EMOJI: dict[str, list[str]] = {
    "hype": ["🔥", "😱", "💥"],
    "funny": ["😂", "💀", "🤣"],
    "chill": ["😌", "✨", "🌙"],
    "informative": ["💡", "📌", "🧠"],
    "dramatic": ["😳", "⚠️", "😬"],
    "wholesome": ["❤️", "🥹", "🙌"],
}
QUESTIONS = [
    "Did that really just happen?",
    "How is this even possible?",
    "Would you have done the same?",
    "Is this the best {topic} moment yet?",
    "Can anyone explain this?",
]
POV: dict[str, list[str]] = {
    "gaming": ["you finally hit the clutch", "your teammate actually listened", "the whole lobby goes quiet",
               "you said 'watch this'"],
    "podcast": ["the conversation takes a turn", "someone says the quiet part out loud",
                "nobody expected that answer"],
    "sports": ["you were there for this", "the crowd loses it", "the comeback starts"],
    "comedy": ["you tried to keep a straight face", "it went exactly as planned"],
    "default": ["you saw it live", "it actually worked", "you hit record at the right time"],
}
MOMENT_WORD = {"gaming": "play", "podcast": "moment", "sports": "play", "comedy": "moment"}

PACKS: dict[str, list[str]] = {
    "gaming": ["#gaming", "#gamer", "#gameplay", "#gamingclips"],
    "podcast": ["#podcast", "#podcastclips", "#interview"],
    "sports": ["#sports", "#highlights"],
    "comedy": ["#comedy", "#funny"],
    "education": ["#tutorial", "#howto", "#tips"],
    "cooking": ["#cooking", "#recipe", "#food"],
    "music": ["#music", "#musician"],
    "vlog": ["#vlog", "#lifestyle"],
    "other": [],
}


def clean_filename(name: str) -> str:
    """'2024-06-01 21-33-12 Ace_on_Ascent (2).mp4' -> 'Ace on Ascent'."""
    stem = Path(name).stem
    stem = DATE_RE.sub(" ", stem)
    stem = TIME_RE.sub(" ", stem)
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)  # camelCase -> camel Case
    words = []
    for tok in re.split(r"[\s_\-.()\[\]{}+]+", stem):
        if not tok or tok.isdigit() or tok.lower() in NOISE:
            continue
        if re.fullmatch(r"[a-f0-9]{8,}", tok.lower()):  # hashes / ids
            continue
        if re.fullmatch(r"(?i)v?\d+|\d+(p|fps|k)", tok):
            continue
        if any(c.isupper() for c in tok):
            words.append(tok)
        elif words and tok.lower() in SMALL_WORDS:
            words.append(tok.lower())
        else:
            words.append(tok.capitalize())
    return " ".join(words)


def pick_topic(profile: dict[str, Any], clip: dict[str, Any]) -> str:
    specifics = split_list(profile.get("specifics", ""))
    haystack = f"{clip.get('filename', '')} {clip.get('folder', '')}".lower()
    squashed = re.sub(r"[\s_\-]", "", haystack)
    for s in specifics:
        if s.lower() in haystack or re.sub(r"\s", "", s.lower()) in squashed:
            return s
    if specifics:
        return specifics[0]
    folder = clean_filename(Path(clip.get("folder") or "").name)
    return folder if len(folder) > 2 else ""


def _target_length(profile: dict[str, Any]) -> int:
    examples = [t for t in (profile.get("example_titles") or "").splitlines() if t.strip()]
    if not examples:
        return 70
    avg = sum(len(t) for t in examples) / len(examples)
    return max(30, min(TITLE_MAX, int(avg * 1.3)))


def _emojify(title: str, tone: str, level: str, rng: random.Random) -> str:
    bank = EMOJI.get(tone, EMOJI["hype"])
    if level == "some":
        return f"{title} {rng.choice(bank)}"
    if level == "lots":
        a, b = rng.sample(bank, 2)
        return f"{a} {title} {b}{b}"
    return title


def sanitize_title(title: str) -> str:
    title = re.sub(r"[<>]", "", title)        # YouTube rejects angle brackets
    title = re.sub(r"\s+", " ", title).strip(" |:-")
    if len(title) > TITLE_MAX:
        title = title[: TITLE_MAX - 1].rsplit(" ", 1)[0].rstrip(" |:-,") + "…"
    return title


def _title(style: str, tone: str, subject: str, topic: str, profile: dict[str, Any],
           rng: random.Random) -> str:
    ctype = profile.get("content_type", "other")
    # Avoid "Clutch: 1v4 Clutch Round" style repeats.
    hooks = [h for h in HOOKS.get(tone, HOOKS["hype"]) if h.lower() not in subject.lower()]
    hook = rng.choice(hooks or HOOKS["hype"])
    thing = subject or (f"this {topic} {MOMENT_WORD.get(ctype, 'moment')}" if topic
                        else f"this {MOMENT_WORD.get(ctype, 'moment')}")
    if style == "question":
        q = rng.choice(QUESTIONS).replace("{topic}", topic or "")
        q = q.replace("  ", " ").replace("the best  moment", "the best moment")
        t = f"{subject}: {q}" if subject else q
    elif style == "pov":
        pov = rng.choice(POV.get(ctype, POV["default"]))
        t = f"POV: {pov}" + (f" | {topic}" if topic else "")
    elif style == "descriptive":
        if subject and topic and topic.lower() not in subject.lower():
            t = f"{subject} | {topic}"
        else:
            t = thing[0].upper() + thing[1:]
    elif style == "caps":
        t = f"{hook.upper()}!! {thing.upper()}"
    else:  # punchy
        t = f"{hook}: {thing}" if rng.random() < 0.6 else f"{thing[0].upper() + thing[1:]} ({hook.lower()})"
    return t


def ranked_styles(profile: dict[str, Any], style_picks: dict[str, int]) -> list[str]:
    preferred = profile.get("title_style", "punchy")
    others = sorted((s for s in TITLE_STYLES if s != preferred),
                    key=lambda s: -int(style_picks.get(s, 0)))
    return [preferred, *others]


def hashtags(profile: dict[str, Any], clip: dict[str, Any], topic: str, short: bool) -> list[str]:
    never = {t.lower() for t in hashtag_list(profile.get("never_tags", ""))}
    ordered = hashtag_list(profile.get("always_tags", ""))
    if topic:
        ordered.append(to_hashtag(topic))
    if short:
        ordered.append("#shorts")
    ordered += PACKS.get(profile.get("content_type", "other"), [])
    out: list[str] = []
    for t in ordered:
        if t and t.lower() not in never and t.lower() not in {o.lower() for o in out}:
            out.append(t)
    return out[:MAX_HASHTAGS]


def keyword_tags(profile: dict[str, Any], subject: str, topic: str) -> list[str]:
    # Only this clip's topic: other games/shows from the profile would be misleading.
    raw = [topic, subject, profile.get("channel_name", "")]
    from ..profile import CONTENT_TYPES
    raw.append(CONTENT_TYPES.get(profile.get("content_type", "other"), ("",))[0])
    out: list[str] = []
    total = 0
    for t in raw:
        t = re.sub(r"[<>,]", "", t or "").strip()
        if t and t.lower() not in {o.lower() for o in out} and total + len(t) + 1 <= TAGS_MAX_CHARS:
            out.append(t)
            total += len(t) + 1
    return out


def description(profile: dict[str, Any], clip: dict[str, Any], tags: list[str]) -> str:
    parts = []
    if clip.get("note"):
        parts.append(clip["note"].strip())
    if profile.get("cta"):
        parts.append(profile["cta"].strip())
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)


def suggest(profile: dict[str, Any], clip: dict[str, Any], style_picks: dict[str, int] | None = None,
            short: bool = False, n: int = 3) -> list[dict[str, Any]]:
    """Return n suggestion dicts: style, title, description, hashtags, tags."""
    rng = random.Random(f"{clip.get('id')}:{clip.get('regen', 0)}")
    subject = clean_filename(clip.get("filename", ""))
    topic = pick_topic(profile, clip)
    if subject and topic and subject.lower() == topic.lower():
        subject = ""
    tones = profile.get("tones") or ["hype"]
    styles = ranked_styles(profile, style_picks or {})
    plan = [(styles[0], tones[0]), (styles[0], tones[-1]), (styles[1], tones[0])][:n]
    target = _target_length(profile)
    tags = hashtags(profile, clip, topic, short)
    keywords = keyword_tags(profile, subject, topic)

    options = []
    seen = set()
    for style, tone in plan:
        for _ in range(6):  # retry a few times to avoid duplicate titles
            t = _title(style, tone, subject, topic, profile, rng)
            if len(t) > target and " | " in t:
                t = t.split(" | ")[0]
            t = sanitize_title(_emojify(t, tone, profile.get("emoji", "some"), rng))
            if t.lower() not in seen:
                break
        seen.add(t.lower())
        options.append({
            "style": style,
            "title": t,
            "description": description(profile, clip, tags),
            "hashtags": tags,
            "tags": keywords,
        })
    return options
