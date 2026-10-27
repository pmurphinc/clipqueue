"""Start ClipQueue: `clipqueue` or `python -m clipqueue`."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(prog="clipqueue", description="Run ClipQueue on this computer.")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--data-dir", help="where ClipQueue keeps its data (default ~/.clipqueue)")
    args = parser.parse_args()
    if args.data_dir:
        os.environ["CLIPQUEUE_HOME"] = args.data_dir

    import uvicorn

    from .app import app

    url = f"http://127.0.0.1:{args.port}/"
    print(f"ClipQueue is running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    # Bound to 127.0.0.1 only: other devices on your network can't reach it.
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
