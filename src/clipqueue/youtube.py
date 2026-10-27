"""YouTube sign-in and uploads, using the person's own Google OAuth client.

The OAuth client JSON and the saved token both live in the local data folder.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import data_dir

# The OAuth redirect comes back to http://127.0.0.1, which oauthlib refuses
# without this. It only affects this local process.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# Google may return scopes in a different order or with extras.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
CHUNK = 8 * 1024 * 1024

_pending_flows: dict[str, Any] = {}


class QuotaError(Exception):
    """YouTube's daily API quota or upload limit was hit."""


class AuthError(Exception):
    """Not connected, or the saved sign-in stopped working."""


def client_secret_path() -> Path:
    return data_dir() / "client_secret.json"


def token_path() -> Path:
    return data_dir() / "youtube_token.json"


def validate_client_secret(raw: bytes) -> str | None:
    """Return an error message, or None if the file looks like a Google OAuth client."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "That file isn't valid JSON."
    if "installed" in data:
        return None
    if "web" in data:
        return ("That's a 'Web application' client. Create an OAuth client of type "
                "'Desktop app' instead (see the setup guide).")
    return "That doesn't look like a Google OAuth client file."


def save_client_secret(raw: bytes) -> None:
    client_secret_path().write_bytes(raw)


def has_client_secret() -> bool:
    return client_secret_path().exists()


def is_connected() -> bool:
    return token_path().exists()


def start_auth(redirect_uri: str) -> str:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        str(client_secret_path()), scopes=SCOPES, redirect_uri=redirect_uri,
        autogenerate_code_verifier=True,
    )
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    _pending_flows[state] = flow
    return url


def has_pending(state: str) -> bool:
    return state in _pending_flows


def finish_auth(state: str, authorization_response: str) -> None:
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise AuthError("Sign-in expired. Please try connecting again.")
    flow.fetch_token(authorization_response=authorization_response)
    token_path().write_text(flow.credentials.to_json(), encoding="utf-8")


def disconnect() -> None:
    try:
        token_path().unlink()
    except FileNotFoundError:
        pass


def _credentials():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not is_connected():
        raise AuthError("YouTube isn't connected.")
    creds = Credentials.from_authorized_user_file(str(token_path()), SCOPES)
    if not creds.valid:
        if not creds.refresh_token:
            raise AuthError("YouTube sign-in expired. Please reconnect.")
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise AuthError(
                "YouTube sign-in expired. Please reconnect. (Google Cloud projects in "
                "'Testing' mode expire sign-ins after 7 days; see the setup guide.)"
            ) from e
        token_path().write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service():
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=_credentials(), cache_discovery=False)


def _reason(err: Any) -> str:
    try:
        return json.loads(err.content)["error"]["errors"][0]["reason"]
    except Exception:
        return ""


def channel_info() -> dict[str, str] | None:
    from googleapiclient.errors import HttpError

    try:
        resp = _service().channels().list(part="snippet", mine=True).execute()
    except HttpError:
        return None
    items = resp.get("items") or []
    if not items:
        return {"title": "(no channel on this account)", "id": ""}
    return {"title": items[0]["snippet"]["title"], "id": items[0]["id"]}


def upload(clip: dict[str, Any], *, category_id: str, made_for_kids: bool,
           publish_at: datetime | None, private_only: bool,
           progress: Callable[[float], None] | None = None) -> dict[str, str]:
    """Upload a clip. Returns {"id", "status"} where status is a human-readable line.

    publish_at (aware datetime in the future): upload private and let YouTube
    publish at that time. None: publish now (or stay private if private_only).
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    tags = [t.strip() for t in (clip.get("tags") or "").split(",") if t.strip()]
    status: dict[str, Any] = {"selfDeclaredMadeForKids": made_for_kids}
    if private_only:
        status["privacyStatus"] = "private"
    elif publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        status["privacyStatus"] = "public"
    body = {
        "snippet": {
            "title": clip["title"],
            "description": clip.get("description") or "",
            "tags": tags,
            "categoryId": category_id,
        },
        "status": status,
    }
    yt = _service()
    media = MediaFileUpload(clip["path"], chunksize=CHUNK, resumable=True)
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            st, resp = req.next_chunk()
            if st and progress:
                progress(st.progress())
    except HttpError as e:
        reason = _reason(e)
        if reason in ("quotaExceeded", "uploadLimitExceeded", "rateLimitExceeded"):
            raise QuotaError(reason) from e
        raise RuntimeError(f"YouTube rejected the upload ({reason or e.resp.status}).") from e
    if progress:
        progress(1.0)
    vid = resp["id"]
    return {"id": vid, "status": _describe_result(yt, vid, status)}


def _describe_result(yt: Any, vid: str, requested: dict[str, Any]) -> str:
    try:
        items = yt.videos().list(part="status", id=vid).execute().get("items") or []
        got = items[0]["status"] if items else {}
    except Exception:
        got = {}
    privacy = got.get("privacyStatus", requested.get("privacyStatus"))
    if requested.get("publishAt") and not got.get("publishAt") and privacy == "private":
        return ("Uploaded, but YouTube kept it private and dropped the schedule. This usually "
                "means your Google Cloud project is unverified; see the setup guide.")
    if requested.get("privacyStatus") == "public" and privacy == "private":
        return ("Uploaded, but YouTube locked it to private. This usually means your Google "
                "Cloud project is unverified; see the setup guide.")
    if got.get("publishAt") or requested.get("publishAt"):
        return "Scheduled on YouTube."
    return {"public": "Published.", "private": "Uploaded as private.",
            "unlisted": "Uploaded as unlisted."}.get(privacy, "Uploaded.")
