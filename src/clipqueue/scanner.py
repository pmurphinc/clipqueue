"""Find video files in the clip folder and read their basic properties."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from . import db
from .config import data_dir

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

# Shared progress for the UI to poll.
scan_state: dict[str, Any] = {"running": False, "done": 0, "total": 0, "message": ""}
_lock = threading.Lock()

# Hide console windows for ffmpeg/ffprobe on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def tool_path(name: str) -> str | None:
    return shutil.which(name)


def probe(path: str) -> dict[str, Any] | None:
    """Return duration (seconds), width and height, or None if ffprobe is missing or fails."""
    exe = tool_path("ffprobe")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW,
        )
        info = json.loads(out.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        return None
    w, h = video.get("width"), video.get("height")
    if w and h and _rotation(video) in (90, 270):
        w, h = h, w
    try:
        duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0) or None
    except ValueError:
        duration = None
    return {"duration": duration, "width": w, "height": h}


def _rotation(stream: dict[str, Any]) -> int:
    rot = stream.get("tags", {}).get("rotate")
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = sd["rotation"]
    try:
        return abs(int(float(rot or 0))) % 360
    except ValueError:
        return 0


def thumbnail(clip: dict[str, Any]) -> Path | None:
    """Make (or reuse) a small JPEG thumbnail. Returns None if ffmpeg is missing."""
    out = data_dir() / "thumbs" / f"{clip['id']}.jpg"
    if out.exists():
        return out
    exe = tool_path("ffmpeg")
    if not exe or not os.path.exists(clip["path"]):
        return None
    at = min(1.0, (clip.get("duration") or 3) / 3)
    try:
        subprocess.run(
            [exe, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", clip["path"],
             "-frames:v", "1", "-vf", "scale=360:-2", str(out)],
            capture_output=True, timeout=30, creationflags=_NO_WINDOW,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return out if out.exists() else None


def find_videos(folder: str) -> list[Path]:
    root = Path(folder)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if Path(f).suffix.lower() in VIDEO_EXTS and not f.startswith("."):
                found.append(Path(dirpath) / f)
    return sorted(found)


def scan(folder: str) -> dict[str, int]:
    """Scan synchronously. Returns counts of added, updated and missing files."""
    with _lock:
        scan_state.update(running=True, done=0, total=0, message="Looking for videos...")
        try:
            return _scan(folder)
        finally:
            scan_state["running"] = False


def _scan(folder: str) -> dict[str, int]:
    videos = find_videos(folder)
    known = db.known_files()
    scan_state.update(total=len(videos), message="Reading clips...")
    added = updated = 0
    seen = set()
    root = Path(folder)
    for i, p in enumerate(videos, 1):
        path = str(p.absolute())
        seen.add(path)
        try:
            st = p.stat()
        except OSError:
            continue
        prev = known.get(path)
        if prev and prev[0] == st.st_size and abs(prev[1] - st.st_mtime) < 1 and prev[2] != "missing":
            scan_state["done"] = i
            continue
        rel_parent = p.parent.relative_to(root).as_posix() if p.parent != root else ""
        folder_name = rel_parent or root.name
        db.upsert_scanned(path, p.name, folder_name, st.st_size, st.st_mtime, probe(path))
        if prev:
            updated += 1
        else:
            added += 1
        scan_state["done"] = i
    root_str = str(root.absolute())
    missing = [k for k in known if k.startswith(root_str) and k not in seen]
    db.mark_missing(missing)
    result = {"found": len(videos), "added": added, "updated": updated, "missing": len(missing)}
    scan_state["message"] = (
        f"Found {result['found']} videos ({added} new, {updated} changed, {len(missing)} missing)."
    )
    return result


def scan_in_background(folder: str) -> bool:
    if scan_state["running"]:
        return False
    threading.Thread(target=scan, args=(folder,), daemon=True).start()
    return True
