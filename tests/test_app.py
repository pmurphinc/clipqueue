import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from clipqueue import db, scanner
from clipqueue.app import app

BASE = "http://127.0.0.1:8765"
SAME_ORIGIN = {"origin": BASE}


@pytest.fixture
def client():
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_rejects_foreign_host(client):
    r = client.get("/", headers={"host": "evil.example"})
    assert r.status_code == 403


def test_rejects_cross_site_post(client):
    r = client.post("/setup/ai", data={}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/setup/ai", data={})  # no origin or referer at all
    assert r.status_code == 403


def test_first_run_goes_to_setup(client):
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/setup/checks"
    for step in ("checks", "folder", "interview", "youtube", "schedule", "ai"):
        assert client.get(f"/setup/{step}").status_code == 200, step


def test_rejects_web_client_secret(client):
    r = client.post("/youtube/client-secret", headers=SAME_ORIGIN,
                    files={"file": ("c.json", b'{"web": {}}', "application/json")},
                    data={"back": "/setup/youtube"}, follow_redirects=False)
    assert "Desktop" in r.headers["location"] or "Desktop" in r.headers["location"].replace("%20", " ")


def make_video(path, w, h, seconds=2):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=15",
         "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_full_flow_scan_suggest_schedule(client, tmp_path):
    clips = tmp_path / "My Clips" / "Valorant"
    clips.mkdir(parents=True)
    make_video(clips / "2024-06-01 ace_on_ascent.mp4", 360, 640)
    make_video(clips / "funny_fail.mp4", 640, 360)

    r = client.post("/setup/folder", headers=SAME_ORIGIN,
                    data={"folder": str(tmp_path / "My Clips"), "back": "/setup/folder"},
                    follow_redirects=False)
    assert r.status_code == 303
    scanner.scan(str((tmp_path / "My Clips").absolute()))  # wait for a full scan
    all_clips = db.list_clips()
    assert len(all_clips) == 2
    short = next(c for c in all_clips if "ace" in c["filename"])
    assert db.is_short(short) and short["folder"] == "Valorant"

    client.post("/setup/interview", headers=SAME_ORIGIN, data={
        "content_type": "gaming", "specifics": "Valorant", "tones": ["hype", "funny"],
        "title_style": "punchy", "emoji": "none", "always_tags": "#mychannel", "next": "/setup/youtube",
    })
    client.post("/setup/schedule", headers=SAME_ORIGIN,
                data={"days": ["0", "1", "2", "3", "4", "5", "6"], "times": "18:00", "next": "/setup/ai"})
    assert client.get("/setup/done").status_code == 200

    r = client.post(f"/api/clip/{short['id']}/suggest", headers=SAME_ORIGIN, data={"ai": "0"})
    opts = r.json()["options"]
    assert r.json()["source"] == "offline"
    assert opts[0]["hashtags"][0] == "#mychannel" and "#shorts" in opts[0]["hashtags"]

    r = client.post(f"/clip/{short['id']}", headers=SAME_ORIGIN, follow_redirects=False,
                    data={"title": opts[0]["title"], "description": opts[0]["description"],
                          "tags": "Valorant", "action": "queue_next"})
    assert r.status_code == 303
    assert db.get_clip(short["id"])["status"] == "queued"

    r = client.post("/queue/autofill", headers=SAME_ORIGIN, data={"count": "5"}, follow_redirects=False)
    assert r.status_code == 303
    queued = db.list_clips("queued")
    assert len(queued) == 2
    assert len({c["scheduled_at"] for c in queued}) == 2  # different slots
    assert all(c["title"] for c in queued)

    for page in ("/queue", "/schedule", "/settings", f"/clip/{short['id']}"):
        assert client.get(page).status_code == 200, page
    assert client.get(f"/thumb/{short['id']}").headers["content-type"] == "image/jpeg"
    r = client.get(f"/media/{short['id']}", headers={"range": "bytes=0-99"})
    assert r.status_code == 206
