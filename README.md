# Shorts bot

Every day this repository makes one English YouTube Short from real news and publishes it automatically.

1. **Researcher** – reads fresh stories from BBC, Sky News, CNN, The Guardian, NPR, Al Jazeera and CBS (`bot/news.py`)
2. **Editor + writer** – Gemini picks the most surprising story and writes a 45-second script (`bot/brain.py`)
3. **Fact-checker** – a second Gemini pass compares title and narration with the articles; failed drafts are dropped
4. **Hashtags** – most-used hashtags of the most viewed similar Shorts this week + Google Trends
5. **Picture editor** – real clips from Pexels, NASA photos (best-looking pick) or AI images from Cloudflare FLUX (`bot/media.py`)
6. **Narrator + animator** – free Kokoro voice, cinematic Remotion animation (`video/`), word-by-word captions, whooshes (`bot/voice.py`, `bot/assemble.py`, `bot/render.py`)
7. **Publisher** – uploads through the official YouTube Data API (`bot/youtube.py`)

It runs on GitHub Actions (`.github/workflows/daily-short.yml`) every day at 15:23 UTC, or by hand from the **Actions** tab.

## Settings
Everything you may want to change is in `config.yaml` (channel name, privacy, voice, number of videos, news feeds).

## Secrets (Settings → Secrets and variables → Actions)
`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `PEXELS_API_KEY`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`.

Optional background music: put royalty-free `.mp3` files (e.g. from the YouTube Audio Library) in `assets/music/`.

## Demo
Push to the `demo` branch (or run **Demo video** in the Actions tab): it renders `samples/sample_story.json` and saves the result on the `demo-output` branch.

## Credits and licences
Animation: [Remotion](https://www.remotion.dev) (free for individuals and teams up to 3). Pictures: Pexels, NASA (public domain), FLUX.1 schnell via Cloudflare. Voice: [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (Apache 2.0).
Fonts: Anton and Montserrat (SIL Open Font License, see `assets/fonts`).
