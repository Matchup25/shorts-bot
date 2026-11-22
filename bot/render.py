"""Agent 5c – the animator: builds the vertical 1080x1920 video, NotebookLM-style."""
import math
import re
import subprocess

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import visuals
from .util import ASSETS, log
from .voice import SR

W, H, FPS = 1080, 1920, 30
BG = (247, 243, 235)
DOT = (225, 217, 202)
INK = (27, 31, 54)
MUTED = (118, 117, 130)
WHITE = (255, 255, 255)
ACCENTS = {
    "science": (98, 76, 230), "space": (88, 70, 220), "tech": (0, 146, 168), "world": (226, 82, 58),
    "business": (24, 146, 92), "health": (0, 128, 214), "nature": (58, 146, 62), "weird": (214, 58, 150),
    "culture": (232, 132, 0),
}
CARD = (80, 225, 1000, 965)           # x0, y0, x1, y1 of the white card
HEADLINE_Y = 1000
CAPTION_Y = 1372                      # everything stays above the Shorts buttons/title area
SAFE_W = 860


# ------------------------------------------------------------------- fonts
def anton(size):
    return ImageFont.truetype(str(ASSETS / "fonts" / "Anton-Regular.ttf"), size)


def mont(size, weight="ExtraBold"):
    font = ImageFont.truetype(str(ASSETS / "fonts" / "Montserrat.ttf"), size)
    font.set_variation_by_name(weight)
    return font


# ------------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_out_back(p, s=1.6):
    p -= 1
    return p * p * ((s + 1) * p + s) + 1


def fade(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return img
    out = img.copy()
    a = out.getchannel("A").point(lambda v: int(v * alpha))
    out.putalpha(a)
    return out


# ------------------------------------------------------------------- layers
def background(accent) -> Image.Image:
    """Cream paper with a dot grid and two soft colour blobs (taller than the frame, so it can drift)."""
    tall = H + 320
    img = Image.new("RGBA", (W, tall), BG + (255,))
    d = ImageDraw.Draw(img)
    for y in range(20, tall, 46):
        for x in range(20, W, 46):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=DOT)
    blobs = Image.new("RGBA", (W, tall), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    bd.ellipse((-260, 120, 520, 900), fill=accent + (46,))
    bd.ellipse((560, 1350, 1400, 2150), fill=accent + (40,))
    bd.ellipse((700, -200, 1300, 380), fill=(255, 190, 90, 40))
    blobs = blobs.filter(ImageFilter.GaussianBlur(110))
    return Image.alpha_composite(img, blobs)


def rounded(size, radius, fill):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=fill)
    return img


def static_layer(channel: str, category: str, sources: list, accent) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # channel pill
    f = mont(34)
    text = channel.upper()
    tw = d.textlength(text, font=f)
    pill_w = int(tw + 92)
    layer.alpha_composite(rounded((pill_w, 70), 35, WHITE + (255,)), (60, 58))
    d.ellipse((86, 80, 112, 106), fill=accent)
    d.text((128, 93), text, font=f, fill=INK, anchor="lm")
    # category chip
    cf = mont(28, "Bold")
    cat = category.upper()
    cw = int(d.textlength(cat, font=cf) + 44)
    layer.alpha_composite(rounded((cw, 52), 26, accent + (255,)), (60 + pill_w + 14, 67))
    d.text((60 + pill_w + 14 + cw / 2, 93), cat, font=cf, fill=WHITE, anchor="mm")
    # sources line
    if sources:
        src = "Source: " + " · ".join(sources[:3])
        d.text((64, 172), src, font=mont(27, "SemiBold"), fill=MUTED, anchor="lm")
    # card with soft shadow
    x0, y0, x1, y1 = CARD
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 6, y0 + 22, x1 - 6, y1 + 26), radius=60, fill=(40, 30, 80, 46))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    layer = Image.alpha_composite(shadow, layer)
    layer.alpha_composite(rounded((x1 - x0, y1 - y0), 58, WHITE + (255,)), (x0, y0))
    return layer


def glow(accent, radius=285) -> Image.Image:
    size = radius * 2 + 120
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((60, 60, size - 60, size - 60), fill=accent + (34,))
    return img.filter(ImageFilter.GaussianBlur(18))


def headline_sprite(text: str, accent) -> Image.Image:
    text = text.upper().strip()
    size = 112
    while True:
        font = anton(size)
        lines = wrap(text, font, 900)
        if len(lines) <= 2 or size <= 64:
            break
        size -= 8
    lh = int(size * 1.06)
    img = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((W / 2 - 50, 0, W / 2 + 50, 10), radius=5, fill=accent)
    for i, line in enumerate(lines):
        d.text((W / 2, 30 + i * lh), line, font=font, fill=INK, anchor="mt")
    return img


def wrap(text, font, max_w):
    words, lines, cur = text.split(), [], ""
    dummy = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for w in words:
        test = (cur + " " + w).strip()
        if dummy.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def photo_card(img: Image.Image) -> Image.Image:
    x0, y0, x1, y1 = CARD
    cw, ch = int((x1 - x0) * 1.12), int((y1 - y0) * 1.12)
    ratio = max(cw / img.width, ch / img.height)
    img = img.resize((int(img.width * ratio) + 1, int(img.height * ratio) + 1), Image.LANCZOS)
    left, top = (img.width - cw) // 2, (img.height - ch) // 2
    return img.crop((left, top, left + cw, top + ch)).convert("RGBA")


# ------------------------------------------------------------------- captions
def caption_chunks(words_per_scene: list) -> list:
    chunks = []
    for words in words_per_scene:
        cur = []
        for w in words:
            cur.append(w)
            if len(cur) == 3 or re.search(r"[.,!?;:]$", w["word"]):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
    for i, ch in enumerate(chunks):
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else ch[-1]["end"] + 0.6
        ch_end = min(nxt, ch[-1]["end"] + 0.35)
        chunks[i] = {"words": ch, "start": ch[0]["start"], "end": ch_end}
    return chunks


class CaptionRenderer:
    def __init__(self, accent):
        self.accent = accent
        self.cache = {}

    def sprite(self, chunk_id: int, chunk: dict, active: int) -> Image.Image:
        key = (chunk_id, active)
        if key in self.cache:
            return self.cache[key]
        words = [re.sub(r"[\"“”]", "", w["word"]) for w in chunk["words"]]
        size = 70
        while True:
            font = mont(size)
            space = font.getlength(" ") + 14
            widths = [font.getlength(w) for w in words]
            total = sum(widths) + space * (len(words) - 1) + 40
            if total <= SAFE_W or size <= 44:
                break
            size -= 4
        hgt = int(size * 1.7)
        img = Image.new("RGBA", (int(total) + 40, hgt), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 40
        for i, (w, wd) in enumerate(zip(words, widths)):
            if i == active:
                d.rounded_rectangle((x - 16, hgt * 0.12, x + wd + 16, hgt * 0.88), radius=18, fill=self.accent)
                d.text((x, hgt / 2), w, font=font, fill=WHITE, anchor="lm")
            else:
                d.text((x, hgt / 2), w, font=font, fill=INK, anchor="lm")
            x += wd + space
        self.cache[key] = img
        return img


# ------------------------------------------------------------------- main
def _stat_text(value: str, p: float) -> str:
    raw = str(value).replace(",", "").strip()
    try:
        num = float(raw)
    except ValueError:
        return str(value)
    cur = num * ease_out_cubic(p)
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return f"{cur:,.{decimals}f}"


def build_video(script: dict, audio: np.ndarray, timings: list, words: list, out_path: str,
                channel: str, sources: list) -> None:
    accent = ACCENTS.get(script["category"], ACCENTS["world"])
    total = len(audio) / SR
    n_frames = int(math.ceil(total * FPS))
    bg = background(accent)
    static = static_layer(channel, script["category"], sources, accent)
    halo = glow(accent)
    captions = CaptionRenderer(accent)
    chunks = caption_chunks(words)
    x0, y0, x1, y1 = CARD
    card_cx, card_cy = (x0 + x1) // 2, (y0 + y1) // 2

    # prepare every scene once
    scenes = []
    for i, sc in enumerate(script["scenes"]):
        vis = sc["visual"]
        item = {"kind": vis["kind"], "head": headline_sprite(sc["headline"] or "", accent),
                "start": timings[i]["start"] - (0.35 if i == 0 else 0.08),
                "end": timings[i + 1]["start"] - 0.08 if i + 1 < len(timings) else total + 1}
        if vis["kind"] == "photo":
            pic = visuals.photo(vis.get("query", ""))
            if pic is not None:
                item["photo"] = photo_card(pic)
                mask = rounded((x1 - x0, y1 - y0), 58, (255, 255, 255, 255)).getchannel("A")
                item["mask"] = mask
            else:
                item["kind"] = "illustration"
        if item["kind"] == "illustration":
            item["art"] = visuals.illustration(vis.get("emoji", "📰"), 520)
        if item["kind"] == "stat":
            item["art"] = visuals.illustration(vis.get("emoji", "📊"), 250)
            item["value"], item["unit"] = vis.get("value", ""), str(vis.get("unit", "")).upper()
        scenes.append(item)

    wav_path = out_path.replace(".mp4", ".wav")
    sf.write(wav_path, audio, SR)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
           "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    stat_font = anton(300)
    unit_font = mont(60)

    for f in range(n_frames):
        t = f / FPS
        yoff = int(160 + 150 * math.sin(t / 7.0))
        frame = bg.crop((0, yoff, W, yoff + H))
        frame.alpha_composite(static)
        d = ImageDraw.Draw(frame)
        # progress bar
        d.rectangle((0, 0, int(W * t / total), 12), fill=accent)

        sc = next((s for s in scenes if s["start"] <= t < s["end"]), scenes[-1])
        u = t - sc["start"]
        p_in = clamp(u / 0.45)
        p_out = clamp((sc["end"] - t) / 0.16)
        alpha = min(ease_out_cubic(p_in), p_out)

        if sc["kind"] == "photo":
            zoom = 1.0 + 0.08 * clamp(u / 6.0)
            ph = sc["photo"]
            cw, ch = x1 - x0, y1 - y0
            vw, vh = int(cw * 1.12 / zoom), int(ch * 1.12 / zoom)
            left, top = (ph.width - vw) // 2, (ph.height - vh) // 2
            view = ph.crop((left, top, left + vw, top + vh)).resize((cw, ch), Image.BILINEAR)
            view.putalpha(sc["mask"].point(lambda v, a=alpha: int(v * a)))
            frame.alpha_composite(view, (x0, y0))
        else:
            pulse = 1 + 0.03 * math.sin(t * 2.2)
            is_stat = sc["kind"] == "stat"
            hs = int(halo.width * pulse * (0.7 + 0.3 * alpha) * (0.5 if is_stat else 1.0))
            h_img = fade(halo.resize((hs, hs), Image.BILINEAR), alpha)
            hcy = y0 + 195 if is_stat else card_cy
            frame.alpha_composite(h_img, (card_cx - hs // 2, hcy - hs // 2))
            scale = 0.55 + 0.45 * ease_out_back(p_in)
            art = sc["art"]
            if abs(scale - 1) > 0.01:
                art = art.resize((max(1, int(art.width * scale)), max(1, int(art.height * scale))), Image.BILINEAR)
            art = fade(art, alpha)
            bob = int(12 * math.sin(t * 2 * math.pi / 3.2))
            if sc["kind"] == "illustration":
                frame.alpha_composite(art, (card_cx - art.width // 2, card_cy - art.height // 2 + bob))
            else:  # stat: small art on top, big counting number, unit
                frame.alpha_composite(art, (card_cx - art.width // 2, y0 + 195 - art.height // 2 + bob))
                num = _stat_text(sc["value"], clamp(u / 0.9))
                layer = Image.new("RGBA", (W, 520), (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                font = stat_font
                while ld.textlength(num, font=font) > 820 and font.size > 120:
                    font = anton(font.size - 20)
                ld.text((W / 2, 200), num, font=font, fill=accent, anchor="mm")
                uf = unit_font
                while ld.textlength(sc["unit"], font=uf) > 800 and uf.size > 30:
                    uf = mont(uf.size - 6)
                ld.text((W / 2, 410), sc["unit"], font=uf, fill=INK, anchor="mm")
                frame.alpha_composite(fade(layer, alpha), (0, y0 + 260))

        # headline
        p_h = clamp((u - 0.05) / 0.35)
        head = fade(sc["head"], min(ease_out_cubic(p_h), p_out))
        frame.alpha_composite(head, (0, HEADLINE_Y + int(40 * (1 - ease_out_cubic(p_h)))))

        # captions
        for ci, chunk in enumerate(chunks):
            if chunk["start"] <= t < chunk["end"]:
                active = 0
                for wi, w in enumerate(chunk["words"]):
                    if t >= w["start"]:
                        active = wi
                spr = captions.sprite(ci, chunk, active)
                pop = clamp((t - chunk["start"]) / 0.12)
                s = 0.86 + 0.14 * ease_out_cubic(pop)
                if s < 0.999:
                    spr = spr.resize((int(spr.width * s), int(spr.height * s)), Image.BILINEAR)
                frame.alpha_composite(spr, (W // 2 - spr.width // 2 - 10, CAPTION_Y - spr.height // 2))
                break

        proc.stdin.write(frame.tobytes())
        if f % 300 == 0:
            log(f"  rendering {int(100 * f / n_frames)}%")
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    log(f"  video ready: {out_path} ({total:.1f}s)")
