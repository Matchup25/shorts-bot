"""Agent 5a – the narrator: free, open-source Kokoro voice (runs on the GitHub server)."""
import re

import numpy as np

from .util import MODELS, log

SR = 24000
GAP = 0.16  # seconds of silence between scenes


def _speech_bounds(samples: np.ndarray, threshold: float = 0.012) -> tuple:
    """Find where speech really starts and ends inside a clip."""
    env = np.abs(samples)
    win = int(SR * 0.02)
    if len(env) < win * 2:
        return 0, len(samples)
    smooth = np.convolve(env, np.ones(win) / win, mode="same")
    idx = np.where(smooth > threshold)[0]
    if not len(idx):
        return 0, len(samples)
    return max(0, idx[0] - win), min(len(samples), idx[-1] + win)


def _word_times(text: str, start: float, end: float) -> list:
    """Spread the words over the spoken time (longer words and pauses get more time)."""
    words = text.split()
    weights = []
    for w in words:
        core = re.sub(r"[^\w]", "", w)
        weight = max(len(core), 2) + 1.2
        if re.search(r"[,;:]$", w):
            weight += 2.5
        elif re.search(r"[.!?]$", w):
            weight += 4.0
        weights.append(weight)
    total = sum(weights) or 1
    out, t = [], start
    for w, weight in zip(words, weights):
        dur = (end - start) * weight / total
        out.append({"word": w, "start": t, "end": t + dur})
        t += dur
    return out


def narrate(scenes: list, voice: str, speed: float) -> tuple:
    """Return (audio samples, scene timings, word timings)."""
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    pieces, timings, words = [np.zeros(int(SR * 0.08), dtype=np.float32)], [], []
    cursor = 0.08
    for i, scene in enumerate(scenes):
        text = scene["narration"].replace("—", ", ").replace("–", ", ")
        lang = "en-gb" if voice.startswith("b") else "en-us"   # British voices need British pronunciation
        samples, sr = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        assert sr == SR
        a, b = _speech_bounds(samples)
        clip = samples[a:b].astype(np.float32)
        dur = len(clip) / SR
        timings.append({"start": cursor, "end": cursor + dur})
        words.append(_word_times(scene["narration"], cursor + 0.03, cursor + dur - 0.05))
        pieces.append(clip)
        gap = GAP if i < len(scenes) - 1 else 0.7
        pieces.append(np.zeros(int(SR * gap), dtype=np.float32))
        cursor += dur + gap
        log(f"  scene {i+1}: {dur:.1f}s of speech")
    audio = np.concatenate(pieces)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.89).astype(np.float32)
    return audio, timings, words
