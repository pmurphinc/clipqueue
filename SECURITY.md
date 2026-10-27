# Security

## How ClipQueue handles your data

- The web app listens on `127.0.0.1` only, so other devices on your network can't reach it.
- It answers only requests addressed to `localhost` / `127.0.0.1`, and rejects form submissions that come from other websites. This protects against DNS-rebinding and cross-site request forgery.
- Your Google OAuth client and token are stored in your local data folder (default `~/.clipqueue`), never in the repo or anywhere else.
- No telemetry and no analytics. The only network calls are to Google (sign-in and uploads) and, if you turn it on, your local `claude` CLI.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** (Security tab → "Report a vulnerability") rather than a public issue. We'll respond as soon as we can.
