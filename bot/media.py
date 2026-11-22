"""Agent 5b – the picture editor: finds a real clip or a beautiful image for every scene.

Order of preference (all free):
  1. Stock VIDEO clips from Pixabay (PIXABAY_API_KEY) or Pexels (PEXELS_API_KEY)
  2. NASA image library for space stories (no key needed, public domain)
  3. AI image from Cloudflare Workers AI / FLUX (needs CF_ACCOUNT_ID + CF_API_TOKEN)
  4. Stock photo from Pixabay / Pexels, then NASA for any topic
  5. A plain designed background (never fails)
"""
import base64
import io
import os
import random
import subprocess

import requests
from PIL import Image, ImageDraw, ImageFilter

from .util import log

UA = {"User-Agent": "ShortsNewsBot/1.0"}
AI_STYLE = (", cinematic photograph, dramatic natural lighting, rich colours, shallow depth of field, "
            "vertical 9:16 composition, highly detailed, no text, no letters, no watermark, no logos")
# for real news events: clearly an illustration, never a fake "photo" of what happened
AI_STYLE_EDITORIAL = (", symbolic editorial illustration, painterly digital art, not photorealistic, "
                      "no recognisable people, no text, no letters, no watermark, no logos")
ORIENTATION = {"value": "portrait"}  # set to "landscape" by the weekly show


def _get(url, **kw):
    kw.setdefault("timeout", 30)
    headers = {**UA, **kw.pop("headers", {})}
    return requests.get(url, headers=headers, **kw)


def _save_image(data: bytes, path: str) -> dict:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if max(img.size) > 2400:
        img.thumbnail((2400, 2400), Image.LANCZOS)
    img.save(path, quality=92)
    return {"width": img.width, "height": img.height}


# ------------------------------------------------------------------ sources
def _prepare_video(raw: str, path: str) -> dict | None:
    """Crop any clip to a sharp vertical 1080x1920, 14 s max, no sound (fast to animate)."""
    w, h = (1920, 1080) if ORIENTATION["value"] == "landscape" else (1080, 1920)
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30"
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-t", "14", "-vf", vf, "-an",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", path],
                       check=True, timeout=300)
        os.remove(raw)
        return {"width": w, "height": h}
    except Exception as exc:
        log(f"    could not prepare clip: {exc}")
        return None


def pixabay_video(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        res = _get("https://pixabay.com/api/videos/",
                   params={"key": key, "q": query[:100], "safesearch": "true", "per_page": 20}).json()
    except Exception as exc:
        log(f"    Pixabay video search failed: {exc}")
        return None
    words = {w for w in query.lower().split() if len(w) > 2}

    def relevance(hit):  # how many search words appear in the clip's tags
        tags = set(str(hit.get("tags", "")).lower().replace(",", " ").split())
        return len(words & tags)

    hits = sorted(res.get("hits", []), key=relevance, reverse=True)
    for hit in hits:
        if ("pb", hit["id"]) in used or hit.get("duration", 0) < 4:
            continue
        files = [f for f in (hit.get("videos") or {}).values() if f.get("url") and f.get("height", 0) >= 1080]
        if not files:
            continue
        best = min(files, key=lambda f: f.get("size") or 10**12)  # smallest file that is still full HD
        raw = path + ".raw.mp4"
        try:
            with open(raw, "wb") as fh:
                fh.write(_get(best["url"], timeout=180).content)
        except Exception:
            continue
        dims = _prepare_video(raw, path)
        if not dims:
            continue
        used.add(("pb", hit["id"]))
        who = hit.get("user", "")
        return {"type": "video", **dims, "credit": f"Video: {who} / Pixabay" if who else "Video: Pixabay"}
    return None


def pixabay_photo(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        orient = "horizontal" if ORIENTATION["value"] == "landscape" else "vertical"
        res = _get("https://pixabay.com/api/", params={"key": key, "q": query[:100], "image_type": "photo",
                                                       "orientation": orient, "safesearch": "true",
                                                       "per_page": 10}).json()
        for hit in res.get("hits", []):
            if ("pbi", hit["id"]) in used:
                continue
            dims = _save_image(_get(hit["largeImageURL"]).content, path)
            used.add(("pbi", hit["id"]))
            return {"type": "image", **dims, "credit": f"Photo: {hit.get('user', '')} / Pixabay"}
    except Exception as exc:
        log(f"    Pixabay photo failed: {exc}")
    return None


def pexels_video(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    for orientation in ("landscape" if ORIENTATION["value"] == "landscape" else "portrait", None):
        params = {"query": query, "per_page": 15, "size": "medium"}
        if orientation:
            params["orientation"] = orientation
        try:
            items = _get("https://api.pexels.com/videos/search", headers={"Authorization": key}, params=params).json()
        except Exception as exc:
            log(f"    Pexels video search failed: {exc}")
            return None
        for video in items.get("videos", []):
            if video["id"] in used or video.get("duration", 0) < 4:
                continue
            files = [f for f in video.get("video_files", [])
                     if f.get("file_type") == "video/mp4" and f.get("height") and 720 <= max(f["width"], f["height"]) <= 2160]
            if not files:
                continue
            best = min(files, key=lambda f: abs(max(f["width"], f["height"]) - 1920))
            raw = path + ".raw.mp4"
            try:
                with open(raw, "wb") as fh:
                    fh.write(_get(best["link"], timeout=180).content)
            except Exception:
                continue
            dims = _prepare_video(raw, path)
            if not dims:
                continue
            used.add(video["id"])
            who = (video.get("user") or {}).get("name", "")
            return {"type": "video", **dims, "credit": f"Video: {who} / Pexels" if who else "Video: Pexels"}
    return None


def pexels_photo(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        items = _get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                     params={"query": query, "per_page": 10,
                             "orientation": "landscape" if ORIENTATION["value"] == "landscape" else "portrait"}).json()
        for photo in items.get("photos", []):
            if photo["id"] in used:
                continue
            dims = _save_image(_get(photo["src"]["large2x"]).content, path)
            used.add(photo["id"])
            return {"type": "image", **dims, "credit": f"Photo: {photo.get('photographer', '')} / Pexels"}
    except Exception as exc:
        log(f"    Pexels photo failed: {exc}")
    return None


BAD_WORDS = ("chart", "graph", "diagram", "plot", "spectrum", "light curve", "map", "logo", "poster", "infographic",
             "comparison", "conference", "briefing", "portrait", "ceremony", "meeting", "award", "panel", "model",
             "schematic", "data", "table", "slide", "illustration of the", "artist's concept of the instrument")


def _look_score(img: Image.Image) -> float:
    """How good a picture looks as a full-screen background: colourful, bright enough, not mostly black."""
    import numpy as np
    a = np.asarray(img.convert("RGB").resize((64, 64)), dtype=np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    rg, yb = r - g, 0.5 * (r + g) - b
    colour = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    lit = float((a.max(axis=2) > 0.18).mean())
    bright = float(a.mean())
    return colour * 3 + lit * 1.2 + min(bright, 0.45)


def nasa_image(query: str, path: str, used: set, min_score: float = 0.75) -> dict | None:
    """Best-looking NASA picture for the query (public domain, no key needed)."""
    if not query:
        return None
    try:
        res = _get("https://images-api.nasa.gov/search",
                   params={"q": query, "media_type": "image", "page_size": 40}).json()
        candidates = []
        for item in res.get("collection", {}).get("items", []):
            meta = (item.get("data") or [{}])[0]
            nasa_id = meta.get("nasa_id")
            text = (meta.get("title", "") + " " + " ".join(meta.get("keywords", []) or [])).lower()
            thumb = next((l.get("href") for l in item.get("links", []) if l.get("render") == "image"), None)
            if not nasa_id or nasa_id in used or not thumb or any(w in text for w in BAD_WORDS):
                continue
            candidates.append((nasa_id, meta, thumb))
            if len(candidates) >= 12:
                break
        scored = []
        for nasa_id, meta, thumb in candidates:
            try:
                img = Image.open(io.BytesIO(_get(thumb.replace("http://", "https://")).content))
                scored.append((_look_score(img), nasa_id, meta))
            except Exception:
                continue
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, nasa_id, meta in scored[:4]:
            if score < min_score:
                break
            assets = _get(f"https://images-api.nasa.gov/asset/{nasa_id}").json()
            hrefs = [a["href"] for a in assets.get("collection", {}).get("items", [])]
            pick = next((h for h in hrefs if "~large" in h and h.lower().endswith(".jpg")), None) or \
                next((h for h in hrefs if "~orig" in h and h.lower().endswith(".jpg")), None)
            if not pick:
                continue
            dims = _save_image(_get(pick.replace("http://", "https://"), timeout=90).content, path)
            if max(dims["width"], dims["height"]) < 900:
                continue
            used.add(nasa_id)
            center = meta.get("center") or ""
            log(f"    NASA pick: {meta.get('title', '')[:60]} (score {score:.2f})")
            return {"type": "image", **dims, "credit": f"Image: NASA{' ' + center if center else ''}"}
    except Exception as exc:
        log(f"    NASA search failed: {exc}")
    return None


def ai_image(prompt: str, path: str, style: str = AI_STYLE) -> dict | None:
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not (account and token and prompt):
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                             json={"prompt": prompt + style, "steps": 8, "seed": random.randint(1, 10**6)},
                             timeout=120)
        data = resp.json()
        b64 = (data.get("result") or {}).get("image")
        if not b64:
            log(f"    AI image refused: {str(data)[:160]}")
            return None
        dims = _save_image(base64.b64decode(b64), path)
        return {"type": "image", **dims, "credit": "AI-generated illustration"}
    except Exception as exc:
        log(f"    AI image failed: {exc}")
        return None


def plain_background(path: str, seed: int) -> dict:
    rnd = random.Random(seed)
    img = Image.new("RGB", (1080, 1920), (12, 12, 20))
    glow = Image.new("RGB", (1080, 1920), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    for _ in range(3):
        x, y, r = rnd.randint(0, 1080), rnd.randint(200, 1700), rnd.randint(300, 600)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.choice([(70, 50, 160), (20, 90, 140), (140, 40, 90)]))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(180)), 0.8)
    img.save(path, quality=92)
    return {"type": "image", "width": 1080, "height": 1920, "credit": ""}


# ------------------------------------------------------------------ main entry
def gather(script: dict, run_dir: str, prefix: str = "scene", used: set | None = None,
           editorial: bool = False) -> list:
    """Return one media description per scene; files are saved in run_dir."""
    used = used if used is not None else set()
    style = AI_STYLE_EDITORIAL if editorial else AI_STYLE
    out = []
    space = script["category"] in {"space", "science"}
    for i, sc in enumerate(script["scenes"]):
        vis = sc["visual"]
        footage = vis.get("footage") or vis.get("query") or ""
        prompt = vis.get("ai_prompt") or ""
        nasa_q = vis.get("nasa") or (footage if space else "")
        if vis.get("kind") == "map":
            out.append(None)
            continue
        base = os.path.join(run_dir, f"{prefix}{i + 1}")
        steps = []
        if space and nasa_q:
            steps.append(("NASA", lambda: nasa_image(nasa_q, base + ".jpg", used)))
        steps += [
            ("Pixabay video", lambda: pixabay_video(footage, base + ".mp4", used)),
            ("Pexels video", lambda: pexels_video(footage, base + ".mp4", used)),
            ("AI image", lambda: ai_image(prompt, base + ".jpg", style)),
            ("Pixabay photo", lambda: pixabay_photo(footage, base + ".jpg", used)),
            ("Pexels photo", lambda: pexels_photo(footage, base + ".jpg", used)),
            ("NASA", lambda: nasa_image(nasa_q or footage, base + ".jpg", used, min_score=0.6)),
        ]
        media = None
        for name, step in steps:
            media = step()
            if media:
                log(f"  scene {i + 1}: {name}")
                break
        if not media:
            log(f"  scene {i + 1}: plain background")
            media = plain_background(base + ".jpg", i)
        ext = ".mp4" if media["type"] == "video" else ".jpg"
        media["src"] = f"run/{prefix}{i + 1}{ext}"
        out.append(media)
    return out
