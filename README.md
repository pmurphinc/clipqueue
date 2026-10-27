# ClipQueue

> Turn a folder of old video clips into a YouTube posting schedule. Runs on your own computer.

**Status: early development.**

## What it does

- Scans a folder of clips and flags which ones qualify as YouTube Shorts
- Asks a short interview about your content, audience, and tone
- Suggests titles, descriptions, and hashtags in your style (works offline; optional AI via your local `claude` CLI)
- Uploads to YouTube on a schedule you choose

YouTube only. See [docs/PLAN.md](docs/PLAN.md) for why TikTok and Instagram aren't supported.

## Principles

- Local-first: runs on `127.0.0.1`, no account, no telemetry
- Free to use: no paid API required
- Your credentials stay on your machine

## License

[MIT](LICENSE)
