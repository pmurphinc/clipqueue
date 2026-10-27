import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own empty ClipQueue data folder."""
    home = tmp_path / "cqhome"
    monkeypatch.setenv("CLIPQUEUE_HOME", str(home))
    return home
