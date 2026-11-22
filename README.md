# Shorts bot

Every day this repository makes one English YouTube Short from real news and publishes it automatically.

1. **Researcher** – reads fresh stories from BBC, Sky News, CNN, The Guardian, NPR, Al Jazeera and CBS (`bot/news.py`)
2. **Editor + writer** – Gemini picks the most surprising story and writes a 45-second script (`bot/brain.py`)
3. **Fact-checker** – a second Gemini pass compares title and narration with the articles; failed drafts are dropped
4. **Hashtags** – most-used hashtags of the most viewed similar Shorts this week + Google Trends
5. **Narrator + animator** – free Kokoro voice, NotebookLM-style animation, word-by-word captions (`bot/voice.py`, `bot/render.py`)
6. **Publisher** – uploads through the official YouTube Data API (`bot/youtube.py`)

It runs on GitHub Actions (`.github/workflows/daily-short.yml`) every day at 15:23 UTC, or by hand from the **Actions** tab.

## Settings
Everything you may want to change is in `config.yaml` (channel name, privacy, voice, number of videos, news feeds).

## Secrets (Settings → Secrets and variables → Actions)
`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, optional `PEXELS_API_KEY`.

## Test locally without any key
```
python scripts/render_sample.py samples/sample_story.json
```

## Credits and licences
Illustrations: [Microsoft Fluent Emoji](https://github.com/microsoft/fluentui-emoji) (MIT). Voice: [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (Apache 2.0).
Fonts: Anton and Montserrat (SIL Open Font License, see `assets/fonts`). Photos (optional): Pexels.
