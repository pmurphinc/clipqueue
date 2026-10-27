# Contributing

Thanks for helping out. ClipQueue is meant to stay small and easy to run.

## Setup

```bash
git clone https://github.com/pmurphinc/clipqueue.git
cd clipqueue
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
clipqueue --data-dir ./.dev-data   # keeps your real ~/.clipqueue untouched
```

`--data-dir` is ignored by git if you keep it under `.dev-data/` or `data/`.

## Guidelines

- **No required cloud services or paid APIs.** Optional integrations must be opt-in and must fall back cleanly.
- **No build step for the UI.** Plain templates, CSS and a little vanilla JS. Don't load scripts from CDNs.
- **Never commit credentials or personal media.** `.gitignore` covers the usual files; double-check before you push.
- Keep the scope to YouTube. Other platforms are out of scope unless their posting APIs become usable by self-hosted apps without per-app review.
- Add or update tests for behavior changes (`pytest`).
