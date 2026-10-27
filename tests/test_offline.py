from clipqueue.generate import offline
from clipqueue.profile import DEFAULT_PROFILE


def profile(**kw):
    p = dict(DEFAULT_PROFILE)
    p.update(kw)
    return p


def test_clean_filename_strips_dates_and_noise():
    assert offline.clean_filename("2024-06-01 21-33-12 Ace_on_Ascent (2).mp4") == "Ace on Ascent"
    assert offline.clean_filename("Replay_2023_11_05-final-EDIT.mov") == ""
    assert offline.clean_filename("clutchRound_1080p_60fps.mp4") == "Clutch Round"
    assert offline.clean_filename("Medal_a1b2c3d4e5f6.mp4") == ""


def test_topic_matches_specifics_in_path():
    p = profile(specifics="Valorant, Rocket League")
    assert offline.pick_topic(p, {"filename": "rocket_league_goal.mp4", "folder": ""}) == "Rocket League"
    assert offline.pick_topic(p, {"filename": "x.mp4", "folder": "misc"}) == "Valorant"


def test_suggestions_are_distinct_and_within_limits():
    p = profile(specifics="Valorant", tones=["hype", "funny"], title_style="pov", emoji="lots")
    clip = {"id": 1, "filename": "ace on ascent.mp4", "folder": "clips", "regen": 0}
    opts = offline.suggest(p, clip, short=True)
    assert len(opts) == 3
    assert len({o["title"] for o in opts}) == 3
    assert opts[0]["style"] == "pov"
    for o in opts:
        assert 0 < len(o["title"]) <= offline.TITLE_MAX
        assert "<" not in o["title"] and ">" not in o["title"]
        assert len(o["hashtags"]) <= offline.MAX_HASHTAGS
        assert "#shorts" in o["hashtags"]


def test_hashtags_respect_always_and_never():
    p = profile(content_type="gaming", specifics="Valorant", always_tags="#MyChannel, fps",
                never_tags="#gamer #gaming")
    tags = offline.hashtags(p, {}, "Valorant", short=False)
    assert tags[:2] == ["#mychannel", "#fps"]
    assert "#valorant" in tags
    assert "#gamer" not in tags and "#gaming" not in tags


def test_regen_changes_output():
    p = profile(specifics="Valorant")
    clip = {"id": 7, "filename": "ace.mp4", "folder": "", "regen": 0}
    a = [o["title"] for o in offline.suggest(p, clip)]
    clip["regen"] = 5
    b = [o["title"] for o in offline.suggest(p, clip)]
    assert a != b


def test_style_picks_rank_second_option():
    p = profile(title_style="punchy")
    styles = offline.ranked_styles(p, {"caps": 4, "pov": 1})
    assert styles[:3] == ["punchy", "caps", "pov"]


def test_sanitize_title_truncates():
    t = offline.sanitize_title("word " * 40)
    assert len(t) <= 100 and t.endswith("…")
