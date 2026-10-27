"""Posting slots and the background uploader.

Clips are uploaded ahead of their slot (up to `upload_ahead_hours` early) as
private with a publish time, so YouTube makes them public on schedule even if
ClipQueue isn't running then.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Iterable

from . import db, youtube
from .config import load_settings
from .profile import category_id, load_profile

# YouTube needs publishAt comfortably in the future; closer than this we just publish now.
MIN_LEAD = timedelta(minutes=15)

state: dict[str, Any] = {"clip_id": None, "progress": 0.0, "message": "Idle.", "paused_until": None}
_wake = threading.Event()
_started = False


def now() -> datetime:
    return datetime.now().astimezone()


def parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def iso(dt: datetime) -> str:
    return dt.replace(second=0, microsecond=0).isoformat()


def slots(settings: dict[str, Any], taken: Iterable[str], count: int,
          start: datetime | None = None) -> list[datetime]:
    """Next `count` free posting slots after `start` (default: now + 15 min)."""
    start = start or (now() + MIN_LEAD)
    days = sorted({int(d) for d in settings.get("schedule_days") or []})
    times = sorted({t for t in settings.get("schedule_times") or [] if _valid_time(t)})
    if not days or not times or count <= 0:
        return []
    taken_set = {iso(d) for d in (parse(t) for t in taken) if d}
    out: list[datetime] = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(366 * 2):
        if day.weekday() in days:
            for t in times:
                h, m = map(int, t.split(":"))
                slot = day.replace(hour=h, minute=m)
                if slot >= start and iso(slot) not in taken_set:
                    out.append(slot)
                    if len(out) == count:
                        return out
        day = (day + timedelta(days=1, hours=2)).replace(hour=0)  # DST-safe step
    return out


def _valid_time(t: str) -> bool:
    try:
        h, m = map(int, str(t).split(":"))
        return 0 <= h < 24 and 0 <= m < 60
    except ValueError:
        return False


def wake() -> None:
    _wake.set()


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="clipqueue-uploader").start()


def _loop() -> None:
    while True:
        try:
            run_once()
        except Exception as e:  # keep the worker alive no matter what
            state["message"] = f"Uploader error: {e}"
        _wake.wait(timeout=60)
        _wake.clear()


def run_once() -> str:
    """Upload at most one due clip. Returns a short description of what happened."""
    settings = load_settings()
    paused = state.get("paused_until")
    if paused and now() < paused:
        return _set(f"Paused until {paused:%a %H:%M} (YouTube daily limit).")
    state["paused_until"] = None
    if not youtube.is_connected():
        return _set("Waiting for YouTube to be connected.")
    clip = db.next_queued()
    if not clip:
        return _set("Idle. Nothing queued.")
    slot = parse(clip["scheduled_at"]) or now()
    if slot - now() > timedelta(hours=float(settings.get("upload_ahead_hours", 72))):
        return _set(f"Next upload starts {slot - timedelta(hours=float(settings.get('upload_ahead_hours', 72))):%a %b %d %H:%M}.")
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    if db.uploads_since(iso(day_start)) >= int(settings.get("daily_upload_cap", 5)):
        state["paused_until"] = day_start + timedelta(days=1)
        return _set("Daily upload cap reached. Resuming tomorrow.")
    return _upload(clip, slot, settings)


def _upload(clip: dict[str, Any], slot: datetime, settings: dict[str, Any]) -> str:
    db.update_clip(clip["id"], status="uploading", error=None)
    state.update(clip_id=clip["id"], progress=0.0, message=f"Uploading {clip['filename']}...")
    private_only = settings.get("publish_mode") == "private"
    publish_at = slot if slot - now() > MIN_LEAD else None

    def progress(p: float) -> None:
        state["progress"] = p

    try:
        result = youtube.upload(
            clip, category_id=category_id(load_profile()),
            made_for_kids=bool(settings.get("made_for_kids")),
            publish_at=publish_at, private_only=private_only, progress=progress,
        )
    except youtube.QuotaError:
        db.update_clip(clip["id"], status="queued")
        state["paused_until"] = now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return _set("YouTube's daily limit was reached. Will retry tomorrow.", clip_id=None)
    except youtube.AuthError as e:
        db.update_clip(clip["id"], status="queued")
        return _set(str(e), clip_id=None)
    except Exception as e:
        db.update_clip(clip["id"], status="failed", error=str(e))
        return _set(f"Upload failed: {e}", clip_id=None)
    db.update_clip(
        clip["id"], status="uploaded", youtube_id=result["id"], youtube_status=result["status"],
        uploaded_at=iso(now()), scheduled_at=iso(publish_at or now()), error=None,
    )
    _wake.set()  # look for the next one right away
    return _set(f"Uploaded {clip['filename']}. {result['status']}", clip_id=None)


def _set(message: str, **extra: Any) -> str:
    state.update(message=message, **extra)
    return message
