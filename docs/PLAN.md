# ClipQueue — project plan

## What it does

Point ClipQueue at a folder of video clips. It walks you through setup, asks a
short interview about your content, then suggests titles, descriptions, and
hashtags in your style and uploads clips to YouTube on a schedule you set.

## Scope

**YouTube only** (regular videos and Shorts). TikTok and Instagram are out of
scope: their posting APIs require per-app review that a self-hosted
open-source tool can't realistically get (TikTok limits unreviewed apps to
private posts; Instagram needs app review and a public video URL).

## Principles

- **Local-first.** Runs on `127.0.0.1`. No ClipQueue account, no telemetry.
- **Free to use.** No paid API required. AI suggestions are opt-in, via your own local `claude` CLI.
- **Your credentials stay local.** OAuth client and token live in your data folder, outside the repo.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| UI | Jinja2 templates, plain CSS, a little vanilla JS (no build step, no CDN) |
| Storage | SQLite + JSON settings in `~/.clipqueue` (override with `CLIPQUEUE_HOME`) |
| Video | `ffprobe` / `ffmpeg` for duration, resolution, thumbnails (optional but recommended) |
| YouTube | `google-api-python-client` + `google-auth-oauthlib`, user's own OAuth client |
| Scheduling | Clips are uploaded ahead of time as private with `publishAt`; YouTube publishes them at the slot time, so the app does not need to be running at publish time |

## Setup wizard

1. **Checks** — Python, ffmpeg/ffprobe, `claude` CLI (optional).
2. **Clip folder** — choose a folder, scan it, see counts and which clips qualify as Shorts.
3. **Interview** — see below.
4. **Connect YouTube** — guided Google Cloud OAuth setup. Skippable (you can draft now, connect later).
5. **Schedule** — days of the week, times, max uploads per day, made-for-kids setting.
6. **AI helper** — opt in to `claude` CLI suggestions if installed.

## Interview (all skippable)

1. What kind of clips are these?
2. Specific games, show, or topics
3. Who's watching?
4. Tone (up to 2)
5. Title style + emoji level
6. 2–5 example titles you like
7. Hashtags to always include / never use
8. Channel name + call-to-action line

## Title and hashtag generation

- **Offline (default):** cleans clip filenames (dates, `clip_001`, recorder noise), picks a topic from your specifics/folder, fills style templates with tone word banks, applies emoji preference and YouTube's 100-character limit. Hashtags = always-include + content-type pack + topic tags − blocklist, capped at 5 (YouTube shows the first 3). Three options per clip; the style you pick most is ranked first next time.
- **AI (opt-in):** sends the profile, example titles, and clip metadata to `claude -p` locally. Falls back to offline on any error.

## Known YouTube caveats

- Uploads from **unverified** Google Cloud projects may be locked to private (Google's docs have changed on this). ClipQueue reads back the video status after upload and tells you if this happened.
- Daily API quota limits uploads per day; ClipQueue has a daily cap setting and retries the next day on `quotaExceeded`.
- There is no API flag for Shorts: YouTube classifies vertical/square videos up to 3 minutes as Shorts automatically.
