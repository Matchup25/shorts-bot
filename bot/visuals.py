"""Agent 5b – the illustrator: free illustrations (Microsoft Fluent Emoji, MIT licence) and free photos (Pexels)."""
import io
import os
import unicodedata
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

from .util import CACHE, log

FLUENT = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


def _names(emoji_char: str) -> list:
    """Possible Fluent folder names for an emoji, e.g. '💡' -> 'Light bulb'."""
    names = []
    try:
        import emoji as emoji_lib
        short = emoji_lib.demojize(emoji_char, language="en").strip(":")
        if short and short != emoji_char:
            names.append(short.replace("_", " "))
    except Exception:
        pass
    base = emoji_char.replace("️", "")
    if base:
        try:
            names.append(unicodedata.name(base[0]).lower())
        except ValueError:
            pass
    out = []
    for n in names:
        n = n.strip()
        if n:
            n = n[0].upper() + n[1:].lower()
            if n not in out:
                out.append(n)
    return out


def _fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def illustration(emoji_char: str, size: int = 620, style: str = "Color") -> Image.Image:
    """Return a transparent RGBA illustration for the emoji."""
    CACHE.mkdir(exist_ok=True)
    key = "".join(f"{ord(c):x}" for c in emoji_char) + f"_{style}_{size}.png"
    cached = CACHE / key
    if cached.exists():
        return Image.open(cached).convert("RGBA")
    img = None
    for name in _names(emoji_char):
        folder = urllib.parse.quote(name)
        file = name.lower().replace(" ", "_").replace("-", "_")
        if style == "Color":
            urls = [f"{FLUENT}/{folder}/Color/{file}_color.svg",
                    f"{FLUENT}/{folder}/Default/Color/{file}_color_default.svg"]
        else:
            urls = [f"{FLUENT}/{folder}/3D/{file}_3d.png",
                    f"{FLUENT}/{folder}/Default/3D/{file}_3d_default.png"]
        for url in urls:
            data = _fetch(url)
            if not data:
                continue
            try:
                if url.endswith(".svg"):
                    import cairosvg
                    png = cairosvg.svg2png(bytestring=data, output_width=size, output_height=size)
                    img = Image.open(io.BytesIO(png)).convert("RGBA")
                else:
                    img = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
                break
            except Exception as exc:
                log(f"  illustration error {name}: {exc}")
        if img:
            break
    if img is None:
        img = _font_emoji(emoji_char, size)
    img.save(cached)
    return img


def _font_emoji(emoji_char: str, size: int) -> Image.Image:
    """Fallback: draw the emoji with the Noto colour emoji font."""
    try:
        font = ImageFont.truetype(EMOJI_FONT, 109)
        canvas = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((80, 80), emoji_char, font=font, embedded_color=True, anchor="mm")
        box = canvas.getbbox()
        if box:
            canvas = canvas.crop(box)
            scale = size / max(canvas.size)
            return canvas.resize((int(canvas.width * scale), int(canvas.height * scale)), Image.LANCZOS)
    except Exception:
        pass
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse((size * 0.2, size * 0.2, size * 0.8, size * 0.8), fill=(120, 120, 200, 255))
    return canvas


def photo(query: str) -> Image.Image | None:
    """Free stock photo from Pexels (needs PEXELS_API_KEY, optional)."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                         params={"query": query, "orientation": "portrait", "per_page": 5}, timeout=20)
        items = r.json().get("photos", [])
        if not items:
            return None
        data = _fetch(items[0]["src"]["large2x"])
        return Image.open(io.BytesIO(data)).convert("RGB") if data else None
    except Exception as exc:
        log(f"  Pexels failed for '{query}': {exc}")
        return None
