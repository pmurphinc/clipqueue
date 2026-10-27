import subprocess

import pytest

from clipqueue import generate
from clipqueue.generate import claude_cli
from clipqueue.profile import DEFAULT_PROFILE

CLIP = {"id": 1, "filename": "goal.mp4", "folder": "Rocket League", "duration": 12, "regen": 0}


def fake_run(stdout, returncode=0):
    def run(*args, **kwargs):
        assert "Rocket League" in kwargs["input"]  # prompt goes in on stdin
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")
    return run


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(claude_cli, "cli_path", lambda: "claude")


def test_parses_options_and_applies_hashtag_rules(cli, monkeypatch):
    out = ('Sure!\n{"options": [{"title": "Overtime <ceiling> shot", "description": "Won it.",'
           ' "hashtags": ["#fyp", "RocketLeague", "#rl"]}]}')
    monkeypatch.setattr(subprocess, "run", fake_run(out))
    p = dict(DEFAULT_PROFILE, always_tags="#mine", never_tags="#fyp")
    opts = claude_cli.suggest(p, CLIP)
    assert opts[0]["title"] == "Overtime ceiling shot"
    assert opts[0]["hashtags"] == ["#mine", "#rocketleague", "#rl"]
    assert opts[0]["description"].startswith("Won it.")


def test_cli_error_falls_back_to_offline(cli, monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_run("Failed to authenticate", returncode=1))
    opts, source = generate.suggest(dict(DEFAULT_PROFILE), CLIP, {"ai_enabled": True}, short=False)
    assert len(opts) == 3
    assert source.startswith("offline") and "Failed to authenticate" in source
