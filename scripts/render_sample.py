"""Render the sample story without Gemini or YouTube (voice + pictures + animation).

Usage:  python scripts/render_sample.py samples/sample_story.json
Pictures come from NASA (no key) and, if the keys are set, Pexels / Cloudflare AI.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import assemble, media, render, voice  # noqa: E402
from bot.util import OUTPUT, load_config, log  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_story.json"
script = json.loads(Path(path).read_text(encoding="utf-8"))
cfg = load_config()
OUTPUT.mkdir(exist_ok=True)
run_dir = render.reset_run_dir()
log("Finding pictures…")
media_list = media.gather(script, run_dir)
log("Narrating…")
audio, timings, words = voice.narrate(script["scenes"], cfg["voice"], cfg["voice_speed"])
duration = assemble.build_mix(audio, timings, f"{run_dir}/mix.wav")
props = assemble.build_props(script, timings, words, media_list, cfg["channel_name"], "run/mix.wav", duration)
out = str(OUTPUT / "sample_short.mp4")
render.render(props, out)
print(out)
