"""Builds the final sound mix and the instructions (props) for the Remotion animation."""
import glob
from pathlib import Path
import json
import random
import subprocess

import numpy as np
import soundfile as sf

from .util import ASSETS, log
from .voice import SR as VOICE_SR

SR = 48000
TRANSITIONS = ["zoom", "whip-left", "zoom", "whip-right", "flash"]


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _whoosh(seed: int, dur: float = 0.5) -> np.ndarray:
    """Synthetic 'whoosh' (filtered noise sweep), no licence needed."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    noise = rng.normal(0, 1, n).astype(np.float32)
    out = np.zeros(n, np.float32)
    y = 0.0
    for i in range(n):
        p = i / n
        cutoff = 7000 * (1 - p) ** 2 + 500
        a = min(1.0, 2 * np.pi * cutoff / SR)
        y += a * (noise[i] - y)
        out[i] = y
    env = np.minimum(np.linspace(0, 1, n) / 0.35, 1) * np.exp(-np.linspace(0, 4.5, n))
    out = out * env
    return out / (np.max(np.abs(out)) + 1e-6)


def _boom(dur: float = 1.2) -> np.ndarray:
    t = np.linspace(0, dur, int(SR * dur), dtype=np.float32)
    freq = 70 * np.exp(-t * 1.5) + 38
    wave = np.sin(2 * np.pi * np.cumsum(freq) / SR)
    return (wave * np.exp(-t * 3.2)).astype(np.float32)


WHOOSH_LEVEL = 0.0   # transition sound between pictures: off (it sounded like paper being torn); was 0.16
LAST_MUSIC: dict = {}   # track used in the last mix, for the credit line in the description


def _music(length: int) -> np.ndarray | None:
    """Background music from assets/music/ (licence and credits: assets/music/CREDITS.md).
    Each video starts the track at a random point, so the same piece sounds different every time."""
    LAST_MUSIC.clear()
    files = sorted(glob.glob(str(ASSETS / "music" / "*.mp3")))
    if not files:
        return None
    path = random.choice(files)
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        m = np.frombuffer(raw, np.float32)
        if len(m) < SR * 5:
            return None
        latest = max(0, len(m) - length - SR * 5)   # leave room so a short video does not hit the track's ending
        start = random.randint(int(SR * 5), latest) if latest > SR * 5 else 0
        m = np.concatenate([m[start:], m[:start]])
        reps = int(np.ceil(length / len(m)))
        m = np.tile(m, reps)[:length].copy()
        fade_in, fade_out = int(SR * 0.8), int(SR * 1.5)
        m[:fade_in] *= np.linspace(0, 1, fade_in)
        m[-fade_out:] *= np.linspace(1, 0, fade_out)
        name = Path(path).stem.split("__")[-1].replace("-", " ").title()
        LAST_MUSIC.update({"title": name, "artist": "Tanner Helland"})
        log(f"  music: {name} (from {start / SR:.0f}s)")
        return m / (np.max(np.abs(m)) + 1e-6)
    except Exception as exc:
        log(f"  music skipped: {exc}")
        return None


def music_credit(short: bool = False) -> str:
    """Credit line required by the music licence (CC BY 4.0); empty when the last video had no music."""
    if not LAST_MUSIC:
        return ""
    if short:
        return f"🎵 \"{LAST_MUSIC['title']}\" by {LAST_MUSIC['artist']} (CC BY 4.0)"
    return (f"Music: \"{LAST_MUSIC['title']}\" by {LAST_MUSIC['artist']}, CC BY 4.0 "
            "(creativecommons.org/licenses/by/4.0), excerpt at low volume. github.com/tannerhelland/free-music")


def build_mix(voice: np.ndarray, timings: list, out_wav: str, whoosh_at: list | None = None) -> float:
    v = _resample(voice, VOICE_SR, SR)
    mix = v * 0.95
    sfx = np.zeros_like(mix)
    boom = _boom()
    sfx[: len(boom)] += boom[: len(sfx)] * 0.35
    points = whoosh_at if whoosh_at is not None else [tm["start"] for tm in timings[1:]]
    for i, at in enumerate(points if WHOOSH_LEVEL else [], start=1):
        w = _whoosh(i)
        start = max(0, int((at - 0.28) * SR))
        end = min(len(sfx), start + len(w))
        sfx[start:end] += w[: end - start] * WHOOSH_LEVEL
    mix = mix + sfx
    music = _music(len(mix))
    if music is not None:
        env = np.abs(v)
        win = int(SR * 0.3)
        env = np.convolve(env, np.ones(win) / win, mode="same")
        duck = np.where(env > 0.02, 0.07, 0.14).astype(np.float32)
        duck = np.convolve(duck, np.ones(win) / win, mode="same")
        mix = mix + music * duck
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = (mix / peak * 0.92).astype(np.float32)
    sf.write(out_wav, mix, SR)
    return len(mix) / SR


def build_props(script: dict, timings: list, words: list, media: list, channel: str, audio_rel: str,
                duration: float) -> dict:
    rnd = random.Random(script["title"])
    offset = rnd.randint(0, len(TRANSITIONS) - 1)
    scenes = []
    for i, (sc, tm, md) in enumerate(zip(script["scenes"], timings, media)):
        vis = sc["visual"]
        if vis.get("kind") == "map" and isinstance(vis.get("place"), dict):
            # geography scene: a globe turns to the place (no picture needed)
            pl = vis["place"]
            scenes.append({
                "start": round(tm["start"], 3), "end": round(tm["end"], 3), "headline": sc["headline"],
                "kind": "map", "media": {"type": "image", "src": ""},
                "place": {"label": str(pl.get("label") or pl.get("country") or "World"),
                          "country": str(pl.get("country") or ""),
                          "lat": float(pl.get("lat") or 0), "lon": float(pl.get("lon") or 0)},
                "transition": TRANSITIONS[(i + offset) % len(TRANSITIONS)],
            })
            continue
        md = md or {"type": "image", "src": ""}
        scene = {
            "start": round(tm["start"], 3),
            "end": round(tm["end"], 3),
            "headline": sc["headline"],
            "kind": "stat" if vis.get("kind") == "stat" and vis.get("value") else "media",
            "media": {k: v for k, v in md.items() if k != "alt"},
            "transition": TRANSITIONS[(i + offset) % len(TRANSITIONS)],
        }
        if md.get("alt"):
            scene["media2"] = md["alt"]
        if scene["kind"] == "stat":
            scene["stat"] = {"value": str(vis.get("value", "")), "unit": str(vis.get("unit", ""))}
        scenes.append(scene)
    flat = [{"text": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
            for scene_words in words for w in scene_words]
    return {
        "channel": channel,
        "category": script["category"],
        "audio": audio_rel,
        "duration": round(duration, 3),
        "scenes": scenes,
        "words": flat,
    }


def write_props(props: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False, indent=1)
