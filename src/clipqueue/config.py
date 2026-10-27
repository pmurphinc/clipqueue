"""Local data folder and app settings.

Everything ClipQueue stores (settings, database, thumbnails, YouTube
credentials) lives in one folder outside the repo: ~/.clipqueue by default,
or wherever CLIPQUEUE_HOME points.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "clip_folder": "",
    "setup_complete": False,
    # Monday=0 ... Sunday=6
    "schedule_days": [0, 2, 4],
    "schedule_times": ["18:00"],
    "daily_upload_cap": 5,
    # Clips are uploaded this many hours before their slot at most.
    "upload_ahead_hours": 72,
    # "schedule": goes public at the slot time. "private": uploads private, you publish manually.
    "publish_mode": "schedule",
    "made_for_kids": False,
    "autofill_order": "oldest",
    "ai_enabled": False,
    # How often each title style was picked; used to rank suggestions.
    "style_picks": {},
}


def data_dir() -> Path:
    d = Path(os.environ.get("CLIPQUEUE_HOME") or Path.home() / ".clipqueue")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":  # POSIX: keep the folder private to this user
        os.chmod(d, 0o700)
    (d / "thumbs").mkdir(exist_ok=True)
    return d


def write_secret(path: Path, data: bytes) -> None:
    """Write a credential file readable only by the current user (0600 on POSIX)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    if os.name != "nt":
        os.chmod(tmp, 0o600)  # in case the file already existed with wider permissions
    os.replace(tmp, path)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    try:
        merged.update(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return merged


def write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_settings() -> dict[str, Any]:
    return read_json(data_dir() / "settings.json", DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    write_json(data_dir() / "settings.json", settings)


def update_settings(**changes: Any) -> dict[str, Any]:
    s = load_settings()
    s.update(changes)
    save_settings(s)
    return s
