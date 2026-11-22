"""Render the sample story without any API key (voice + animation only).

Usage:  python scripts/render_sample.py samples/sample_story.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import render, voice  # noqa: E402
from bot.util import OUTPUT, load_config, log  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_story.json"
script = json.loads(Path(path).read_text(encoding="utf-8"))
cfg = load_config()
OUTPUT.mkdir(exist_ok=True)
log("Narrating…")
audio, timings, words = voice.narrate(script["scenes"], cfg["voice"], cfg["voice_speed"])
log("Animating…")
out = str(OUTPUT / "sample_short.mp4")
render.build_video(script, audio, timings, words, out, cfg["channel_name"], script.get("sources", []))
print(out)
