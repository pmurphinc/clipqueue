"""FastAPI app: setup wizard, clip queue, clip editor, schedule, settings."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, db, generate, scanner, scheduler, youtube
from .config import data_dir, load_settings, save_settings, update_settings
from .generate import claude_cli
from .profile import (CONTENT_TYPES, EMOJI_LEVELS, TITLE_STYLES, TONES, load_profile,
                      profile_from_form, save_profile)

HERE = Path(__file__).parent
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}

SETUP_STEPS = [
    ("checks", "Checks"),
    ("folder", "Clip folder"),
    ("interview", "Your content"),
    ("youtube", "YouTube"),
    ("schedule", "Schedule"),
    ("ai", "AI helper"),
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    scheduler.start()
    yield


app = FastAPI(title="ClipQueue", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


# ---------- template helpers ----------

def fmt_time(value: str | None) -> str:
    dt = scheduler.parse(value)
    return dt.strftime("%a %b %d, %I:%M %p").replace(" 0", " ") if dt else ""


def fmt_duration(sec: float | None) -> str:
    if not sec:
        return "?"
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


templates.env.filters["when"] = fmt_time
templates.env.filters["dur"] = fmt_duration
templates.env.globals.update(is_short=db.is_short, version=__version__, weekdays=WEEKDAYS)


def render(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    ctx.setdefault("settings", load_settings())
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx.setdefault("err", request.query_params.get("err", ""))
    return templates.TemplateResponse(request, name, ctx)


def go(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if err:
        url += ("&" if "?" in url else "?") + "err=" + quote(err)
    return RedirectResponse(url, status_code=303)


def require_clip(clip_id: int) -> dict[str, Any]:
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    return clip


# ---------- security: only this machine, only this app ----------

@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "")
    hostname = urlparse(f"//{host}").hostname or ""
    if hostname not in LOCAL_HOSTS and f"[{hostname}]" not in LOCAL_HOSTS:
        return Response("ClipQueue only answers on localhost.", status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # Block other websites from submitting forms to this app.
        source = request.headers.get("origin") or request.headers.get("referer") or ""
        if urlparse(source).netloc != host:
            return Response("Request blocked: it didn't come from ClipQueue.", status_code=403)
    return await call_next(request)


# ---------- home + OAuth return ----------

@app.get("/")
def home(request: Request):
    code, state = request.query_params.get("code"), request.query_params.get("state")
    if state and (code or request.query_params.get("error")):
        return _oauth_return(request, state)
    if not load_settings().get("setup_complete"):
        return go("/setup/checks")
    return go("/queue")


def _oauth_return(request: Request, state: str) -> RedirectResponse:
    back = "/setup/youtube" if not load_settings().get("setup_complete") else "/settings#youtube"
    if request.query_params.get("error"):
        return go(back, err="Google sign-in was cancelled.")
    try:
        youtube.finish_auth(state, str(request.url))
    except Exception as e:
        return go(back, err=f"Couldn't finish connecting: {e}")
    return go(back, msg="YouTube connected.")


# ---------- setup wizard ----------

def _step_ctx(step: str) -> dict[str, Any]:
    keys = [k for k, _ in SETUP_STEPS]
    i = keys.index(step)
    return {
        "steps": SETUP_STEPS, "step": step, "step_index": i,
        "next_step": keys[i + 1] if i + 1 < len(keys) else "done",
        "prev_step": keys[i - 1] if i > 0 else None,
    }


def _checks() -> list[dict[str, Any]]:
    py_ok = sys.version_info >= (3, 11)
    ffprobe, ffmpeg, claude = scanner.tool_path("ffprobe"), scanner.tool_path("ffmpeg"), claude_cli.cli_path()
    os_name = platform.system()
    ff_hint = {
        "Windows": "winget install Gyan.FFmpeg",
        "Darwin": "brew install ffmpeg",
    }.get(os_name, "sudo apt install ffmpeg  (or your distro's package manager)")
    return [
        {"name": "Python 3.11+", "ok": py_ok, "detail": platform.python_version(), "required": True},
        {"name": "ffprobe / ffmpeg", "ok": bool(ffprobe and ffmpeg),
         "detail": "found" if ffprobe and ffmpeg else f"Not found. Install with: {ff_hint}",
         "required": False,
         "why": "Reads clip length and shape, makes thumbnails. ClipQueue works without it, "
                "but can't tell which clips are Shorts."},
        {"name": "claude CLI", "ok": bool(claude), "detail": "found" if claude else "not installed",
         "required": False, "why": "Optional. Enables AI title suggestions using your own Claude plan."},
    ]


@app.get("/setup")
def setup_root():
    return go("/setup/checks")


@app.get("/setup/{step}")
def setup_step(request: Request, step: str):
    if step == "done":
        update_settings(setup_complete=True)
        return render(request, "setup_done.html", counts=db.counts())
    if step not in dict(SETUP_STEPS):
        raise HTTPException(404)
    ctx = _step_ctx(step)
    ctx.update(_page_ctx(step))
    return render(request, f"setup_{step}.html", **ctx)


def _page_ctx(section: str) -> dict[str, Any]:
    if section == "checks":
        return {"checks": _checks()}
    if section == "folder":
        return {"scan": scanner.scan_state, "counts": db.counts(),
                "home": str(Path.home())}
    if section == "interview":
        return {"profile": load_profile(), "content_types": CONTENT_TYPES, "tones": TONES,
                "title_styles": TITLE_STYLES, "emoji_levels": EMOJI_LEVELS}
    if section == "youtube":
        ctx: dict[str, Any] = {"has_secret": youtube.has_client_secret(),
                               "connected": youtube.is_connected(), "channel": None}
        if ctx["connected"]:
            try:
                ctx["channel"] = youtube.channel_info()
            except youtube.AuthError as e:
                ctx["connected"], ctx["auth_error"] = False, str(e)
        return ctx
    if section == "schedule":
        return {}
    if section == "ai":
        return {"claude_path": claude_cli.cli_path()}
    return {}


@app.post("/setup/folder")
async def setup_folder(request: Request):
    form = await request.form()
    folder = str(form.get("folder", "")).strip().strip('"')
    back = str(form.get("back", "/setup/folder"))
    if not folder or not os.path.isdir(folder):
        return go(back, err=f"Folder not found: {folder or '(empty)'}")
    # abspath, not resolve(): keep mapped/network drive letters as the user typed them.
    folder = os.path.abspath(folder)
    update_settings(clip_folder=folder)
    scanner.scan_in_background(folder)
    return go(back, msg="Scanning your folder...")


@app.post("/rescan")
async def rescan(request: Request):
    folder = load_settings().get("clip_folder")
    if not folder or not os.path.isdir(folder):
        return go("/settings", err="Set a clip folder first.")
    scanner.scan_in_background(folder)
    return go(_back(request, "/queue"), msg="Rescanning...")


@app.get("/api/scan")
def scan_status():
    return JSONResponse({**scanner.scan_state, "counts": db.counts()})


@app.post("/setup/interview")
async def setup_interview(request: Request):
    form = await request.form()
    save_profile(profile_from_form(form))
    return go(str(form.get("next", "/setup/youtube")), msg="Saved.")


@app.post("/youtube/client-secret")
async def youtube_client_secret(request: Request):
    form = await request.form()
    back = str(form.get("back", "/setup/youtube"))
    upload = form.get("file")
    raw = await upload.read() if upload is not None and hasattr(upload, "read") else b""
    if not raw:
        return go(back, err="Choose the JSON file you downloaded from Google Cloud.")
    if len(raw) > 64_000:
        return go(back, err="That file is too large to be an OAuth client file.")
    problem = youtube.validate_client_secret(raw)
    if problem:
        return go(back, err=problem)
    youtube.save_client_secret(raw)
    return go(back, msg="OAuth client saved. Now connect your channel.")


@app.post("/youtube/connect")
async def youtube_connect(request: Request):
    if not youtube.has_client_secret():
        return go(_back(request, "/setup/youtube"), err="Add your OAuth client file first.")
    redirect_uri = str(request.base_url)  # e.g. http://127.0.0.1:8765/
    try:
        url = youtube.start_auth(redirect_uri)
    except Exception as e:
        return go(_back(request, "/setup/youtube"), err=f"Couldn't start sign-in: {e}")
    return RedirectResponse(url, status_code=303)


@app.post("/youtube/disconnect")
async def youtube_disconnect(request: Request):
    youtube.disconnect()
    return go(_back(request, "/settings"), msg="YouTube disconnected.")


@app.post("/setup/schedule")
async def setup_schedule(request: Request):
    form = await request.form()
    days = sorted({int(d) for d in form.getlist("days") if str(d).isdigit() and 0 <= int(d) <= 6})
    times = [t.strip() for t in str(form.get("times", "")).split(",") if scheduler._valid_time(t.strip())]
    s = load_settings()
    s.update(
        schedule_days=days or s["schedule_days"],
        schedule_times=sorted(set(times)) or s["schedule_times"],
        daily_upload_cap=max(1, min(50, _int(form.get("daily_upload_cap"), 5))),
        upload_ahead_hours=max(1, min(240, _int(form.get("upload_ahead_hours"), 72))),
        publish_mode="private" if form.get("publish_mode") == "private" else "schedule",
        made_for_kids=form.get("made_for_kids") == "yes",
        autofill_order="newest" if form.get("autofill_order") == "newest" else "oldest",
    )
    save_settings(s)
    scheduler.wake()
    return go(str(form.get("next", "/setup/ai")), msg="Saved.")


@app.post("/setup/ai")
async def setup_ai(request: Request):
    form = await request.form()
    update_settings(ai_enabled=form.get("ai_enabled") == "on" and bool(claude_cli.cli_path()))
    return go(str(form.get("next", "/setup/done")), msg="Saved.")


def _int(v: Any, default: int) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return default


def _back(request: Request, default: str) -> str:
    """Path of the page the form was submitted from (without its query string)."""
    return urlparse(request.headers.get("referer", "")).path or default


# ---------- queue ----------

QUEUE_FILTERS = [("all", "All"), ("new", "New"), ("draft", "Drafts"), ("queued", "Scheduled"),
                 ("uploaded", "Posted"), ("failed", "Failed"), ("skipped", "Skipped")]


@app.get("/queue")
def queue(request: Request, status: str = "all", kind: str = "any"):
    clips = db.list_clips(None if status == "all" else status)
    if status == "all":
        clips = [c for c in clips if c["status"] != "missing"]
    if kind == "short":
        clips = [c for c in clips if db.is_short(c)]
    elif kind == "long":
        clips = [c for c in clips if not db.is_short(c)]
    return render(request, "queue.html", clips=clips, status=status, kind=kind,
                  filters=QUEUE_FILTERS, counts=db.counts(), scan=scanner.scan_state,
                  uploader=scheduler.state, connected=youtube.is_connected())


@app.post("/queue/autofill")
async def autofill(request: Request):
    form = await request.form()
    count = max(1, min(100, _int(form.get("count"), 7)))
    only_shorts = form.get("only_shorts") == "on"
    settings, profile = load_settings(), load_profile()
    order = "mtime ASC" if settings.get("autofill_order") == "oldest" else "mtime DESC"
    pool = [c for c in db.list_clips(order=order) if c["status"] in ("new", "draft")
            and os.path.exists(c["path"]) and (not only_shorts or db.is_short(c))][:count]
    if not pool:
        return go("/queue", err="No new or draft clips to schedule.")
    free = scheduler.slots(settings, db.taken_slots(), len(pool))
    if not free:
        return go("/queue", err="Set at least one posting day and time in Settings.")
    for clip, slot in zip(pool, free):
        fields: dict[str, Any] = {"status": "queued", "scheduled_at": scheduler.iso(slot)}
        if not clip["title"]:
            opt = generate.offline.suggest(profile, clip, settings.get("style_picks"), db.is_short(clip))[0]
            fields.update(title=opt["title"], description=opt["description"], tags=", ".join(opt["tags"]))
        db.update_clip(clip["id"], **fields)
    scheduler.wake()
    return go("/schedule", msg=f"Scheduled {min(len(pool), len(free))} clips. Review them below; "
                               "nothing uploads until it's within the upload window.")


# ---------- clip editor ----------

@app.get("/clip/{clip_id}")
def clip_page(request: Request, clip_id: int):
    clip = require_clip(clip_id)
    settings = load_settings()
    next_slot = scheduler.slots(settings, db.taken_slots(), 1)
    return render(request, "clip.html", clip=clip, short=db.is_short(clip),
                  exists=os.path.exists(clip["path"]),
                  next_slot=scheduler.iso(next_slot[0]) if next_slot else None,
                  ai_available=bool(claude_cli.cli_path()), uploader=scheduler.state)


@app.get("/media/{clip_id}")
def media(clip_id: int):
    clip = require_clip(clip_id)
    if not os.path.exists(clip["path"]):
        raise HTTPException(404)
    return FileResponse(clip["path"])


@app.get("/thumb/{clip_id}")
def thumb(clip_id: int):
    clip = require_clip(clip_id)
    p = scanner.thumbnail(clip)
    if not p:
        return FileResponse(HERE / "static" / "no-thumb.svg", media_type="image/svg+xml")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.post("/api/clip/{clip_id}/suggest")
async def suggest(request: Request, clip_id: int):
    form = await request.form()
    clip = require_clip(clip_id)
    regen = clip["regen"] + 1
    db.update_clip(clip_id, regen=regen)
    clip["regen"] = regen
    if form.get("note") is not None:
        clip["note"] = str(form.get("note"))
    use_ai = form.get("ai") == "1"
    options, source = generate.suggest(load_profile(), clip, load_settings(), db.is_short(clip), use_ai)
    return JSONResponse({"options": options, "source": source})


@app.post("/api/style-pick")
async def style_pick(request: Request):
    form = await request.form()
    style = str(form.get("style", ""))
    if style in TITLE_STYLES:
        s = load_settings()
        picks = s.get("style_picks", {})
        picks[style] = int(picks.get(style, 0)) + 1
        s["style_picks"] = picks
        save_settings(s)
    return JSONResponse({"ok": True})


@app.post("/clip/{clip_id}")
async def clip_save(request: Request, clip_id: int):
    clip = require_clip(clip_id)
    form = await request.form()
    action = str(form.get("action", "save"))
    if clip["status"] in ("uploading", "uploaded"):
        return go(f"/clip/{clip_id}", err="This clip is already on YouTube; edit it there.")
    title = str(form.get("title", "")).strip()
    fields: dict[str, Any] = {
        "title": generate.offline.sanitize_title(title) if title else "",
        "description": str(form.get("description", "")).strip()[:4900],
        "tags": str(form.get("tags", "")).strip()[:500],
        "note": str(form.get("note", "")).strip()[:1000],
    }
    if action in ("queue_next", "queue_at", "upload_now") and not fields["title"]:
        db.update_clip(clip_id, **fields, status="draft" if clip["status"] == "new" else clip["status"])
        return go(f"/clip/{clip_id}", err="Add a title first.")

    if action == "queue_next":
        free = scheduler.slots(load_settings(), db.taken_slots() - {clip["scheduled_at"]}, 1)
        if not free:
            return go(f"/clip/{clip_id}", err="Set posting days and times in Settings first.")
        fields.update(status="queued", scheduled_at=scheduler.iso(free[0]), error=None)
    elif action == "queue_at":
        when = scheduler.parse(str(form.get("when", "")))
        if not when or when < scheduler.now():
            return go(f"/clip/{clip_id}", err="Pick a time in the future.")
        fields.update(status="queued", scheduled_at=scheduler.iso(when), error=None)
    elif action == "upload_now":
        fields.update(status="queued", scheduled_at=scheduler.iso(scheduler.now()), error=None)
    elif action == "unqueue":
        fields.update(status="draft", scheduled_at=None)
    elif action == "skip":
        fields.update(status="skipped", scheduled_at=None)
    elif action == "unskip":
        fields.update(status="draft")
    elif clip["status"] in ("new", "skipped"):
        fields["status"] = "draft"
    db.update_clip(clip_id, **fields)
    scheduler.wake()
    msgs = {"queue_next": "Scheduled.", "queue_at": "Scheduled.", "unqueue": "Unscheduled.",
            "skip": "Skipped.", "unskip": "Moved back to drafts.",
            "upload_now": "Queued for upload now." if youtube.is_connected()
            else "Queued. It will upload once YouTube is connected."}
    return go(f"/clip/{clip_id}", msg=msgs.get(action, "Saved."))


@app.post("/clip/{clip_id}/retry")
async def clip_retry(clip_id: int):
    clip = require_clip(clip_id)
    if clip["status"] == "failed":
        when = scheduler.parse(clip["scheduled_at"])
        if not when or when < scheduler.now():
            when = scheduler.now()
        db.update_clip(clip_id, status="queued", error=None, scheduled_at=scheduler.iso(when))
        scheduler.wake()
    return go("/schedule", msg="Retrying.")


# ---------- schedule ----------

@app.get("/schedule")
def schedule(request: Request):
    return render(
        request, "schedule.html",
        queued=db.list_clips("queued", "scheduled_at ASC") + db.list_clips("uploading"),
        failed=db.list_clips("failed"),
        uploaded=db.list_clips("uploaded", "uploaded_at DESC")[:50],
        uploader=scheduler.state, connected=youtube.is_connected(),
    )


@app.get("/api/uploader")
def uploader_status():
    s = dict(scheduler.state)
    s["paused_until"] = s["paused_until"].isoformat() if isinstance(s.get("paused_until"), datetime) else None
    return JSONResponse(s)


@app.post("/api/uploader/run")
async def uploader_run():
    scheduler.wake()
    return JSONResponse({"ok": True})


# ---------- settings ----------

@app.get("/settings")
def settings_page(request: Request):
    ctx: dict[str, Any] = {"data_dir": str(data_dir())}
    for section in ("folder", "interview", "youtube", "ai"):
        ctx.update(_page_ctx(section))
    return render(request, "settings.html", **ctx)
