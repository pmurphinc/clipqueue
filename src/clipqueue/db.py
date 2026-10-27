"""SQLite storage for the clip library."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import data_dir

# Clip status values:
#   new       found by the scanner, untouched
#   draft     has edits but isn't scheduled
#   queued    scheduled; waiting to be uploaded
#   uploading upload in progress
#   uploaded  on YouTube
#   failed    upload failed (see error)
#   skipped   user chose not to post it
#   missing   file is gone from disk
STATUSES = ["new", "draft", "queued", "uploading", "uploaded", "failed", "skipped", "missing"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id             INTEGER PRIMARY KEY,
    path           TEXT UNIQUE NOT NULL,
    filename       TEXT NOT NULL,
    folder         TEXT NOT NULL DEFAULT '',
    size           INTEGER NOT NULL DEFAULT 0,
    mtime          REAL NOT NULL DEFAULT 0,
    duration       REAL,
    width          INTEGER,
    height         INTEGER,
    status         TEXT NOT NULL DEFAULT 'new',
    title          TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    tags           TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    scheduled_at   TEXT,
    youtube_id     TEXT,
    youtube_status TEXT,
    error          TEXT,
    uploaded_at    TEXT,
    regen          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
"""

EDITABLE = {
    "status", "title", "description", "tags", "note", "scheduled_at", "youtube_id",
    "youtube_status", "error", "uploaded_at", "regen", "duration", "width", "height",
    "size", "mtime",
}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(data_dir() / "clipqueue.db", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")
        # An upload interrupted by a restart starts over.
        c.execute("UPDATE clips SET status='queued' WHERE status='uploading'")


def get_clip(clip_id: int) -> dict[str, Any] | None:
    with connect() as c:
        row = c.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    return dict(row) if row else None


def list_clips(status: str | None = None, order: str = "mtime DESC") -> list[dict[str, Any]]:
    allowed = {"mtime DESC", "mtime ASC", "scheduled_at ASC", "uploaded_at DESC"}
    if order not in allowed:
        order = "mtime DESC"
    q = "SELECT * FROM clips"
    args: tuple[Any, ...] = ()
    if status:
        q += " WHERE status=?"
        args = (status,)
    with connect() as c:
        return [dict(r) for r in c.execute(f"{q} ORDER BY {order}", args)]


def counts() -> dict[str, int]:
    with connect() as c:
        rows = c.execute("SELECT status, COUNT(*) n FROM clips GROUP BY status").fetchall()
    out = {s: 0 for s in STATUSES}
    out.update({r["status"]: r["n"] for r in rows})
    out["all"] = sum(v for k, v in out.items() if k != "missing")
    return out


def update_clip(clip_id: int, **fields: Any) -> None:
    bad = set(fields) - EDITABLE
    if bad:
        raise ValueError(f"not editable: {bad}")
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE clips SET {cols} WHERE id=?", (*fields.values(), clip_id))


def upsert_scanned(path: str, filename: str, folder: str, size: int, mtime: float,
                   probe: dict[str, Any] | None) -> None:
    probe = probe or {}
    with connect() as c:
        c.execute(
            """INSERT INTO clips (path, filename, folder, size, mtime, duration, width, height)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET
                 size=excluded.size, mtime=excluded.mtime, duration=excluded.duration,
                 width=excluded.width, height=excluded.height,
                 status=CASE WHEN clips.status='missing' THEN 'new' ELSE clips.status END""",
            (path, filename, folder, size, mtime,
             probe.get("duration"), probe.get("width"), probe.get("height")),
        )


def known_files() -> dict[str, tuple[int, float, str]]:
    with connect() as c:
        return {r["path"]: (r["size"], r["mtime"], r["status"])
                for r in c.execute("SELECT path, size, mtime, status FROM clips")}


def mark_missing(paths: list[str]) -> None:
    with connect() as c:
        c.executemany(
            "UPDATE clips SET status='missing' WHERE path=? AND status IN ('new','draft','skipped')",
            [(p,) for p in paths],
        )


def taken_slots() -> set[str]:
    with connect() as c:
        rows = c.execute(
            "SELECT scheduled_at FROM clips WHERE status IN ('queued','uploading','uploaded') "
            "AND scheduled_at IS NOT NULL"
        ).fetchall()
    return {r["scheduled_at"] for r in rows}


def uploads_since(iso_time: str) -> int:
    with connect() as c:
        return c.execute(
            "SELECT COUNT(*) FROM clips WHERE uploaded_at >= ?", (iso_time,)
        ).fetchone()[0]


def next_queued() -> dict[str, Any] | None:
    with connect() as c:
        row = c.execute(
            "SELECT * FROM clips WHERE status='queued' ORDER BY scheduled_at ASC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def is_short(clip: dict[str, Any]) -> bool:
    """YouTube treats vertical or square videos up to 3 minutes as Shorts."""
    d, w, h = clip.get("duration"), clip.get("width"), clip.get("height")
    return bool(d and w and h and d <= 180 and h >= w)
