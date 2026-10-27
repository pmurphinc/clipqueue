from datetime import datetime

from clipqueue import scheduler


def local(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi).astimezone()


def test_slots_follow_days_and_times():
    settings = {"schedule_days": [0, 2], "schedule_times": ["18:00", "09:30"]}
    start = local(2026, 11, 2, 10, 0)  # a Monday, 10:00
    got = scheduler.slots(settings, [], 4, start=start)
    assert [(s.weekday(), s.hour, s.minute) for s in got] == [
        (0, 18, 0), (2, 9, 30), (2, 18, 0), (0, 9, 30)
    ]


def test_slots_skip_taken():
    settings = {"schedule_days": [0], "schedule_times": ["18:00"]}
    start = local(2026, 11, 2, 10, 0)
    taken = [scheduler.iso(local(2026, 11, 2, 18, 0))]
    got = scheduler.slots(settings, taken, 1, start=start)
    assert got[0].date().isoformat() == "2026-11-09"


def test_slots_empty_without_days():
    assert scheduler.slots({"schedule_days": [], "schedule_times": ["18:00"]}, [], 3) == []


def test_run_once_waits_without_youtube():
    from clipqueue import db

    db.init()
    assert "connected" in scheduler.run_once()


def test_write_secret_is_owner_only(tmp_path):
    import os
    import stat

    from clipqueue.config import write_secret

    p = tmp_path / "token.json"
    write_secret(p, b"{}")
    assert p.read_bytes() == b"{}"
    if os.name != "nt":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
