"""Agent 5b – the picture editor: finds a real clip or a beautiful image for every scene.

Order of preference (all free):
  1. Pexels stock VIDEO clips (needs PEXELS_API_KEY)
  2. NASA image library for space stories (no key needed, public domain)
  3. AI image from Cloudflare Workers AI / FLUX (needs CF_ACCOUNT_ID + CF_API_TOKEN)
  4. Pexels stock photo, then NASA for any topic
  5. A plain designed background (never fails)
"""
import base64
import io
import os
import random

import requests
from PIL import Image, ImageDraw, ImageFilter

from .util import log

UA = {"User-Agent": "ShortsNewsBot/1.0"}
AI_STYLE = (", cinematic photograph, dramatic natural lighting, rich colours, shallow depth of field, "
            "vertical 9:16 composition, highly detailed, no text, no letters, no watermark, no logos")


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
def pexels_video(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    for orientation in ("portrait", None):
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
            try:
                data = _get(best["link"], timeout=120).content
            except Exception:
                continue
            with open(path, "wb") as fh:
                fh.write(data)
            used.add(video["id"])
            who = (video.get("user") or {}).get("name", "")
            return {"type": "video", "width": best["width"], "height": best["height"],
                    "credit": f"Video: {who} / Pexels" if who else "Video: Pexels"}
    return None


def pexels_photo(query: str, path: str, used: set) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not query:
        return None
    try:
        items = _get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait", "per_page": 10}).json()
        for photo in items.get("photos", []):
            if photo["id"] in used:
                continue
            dims = _save_image(_get(photo["src"]["large2x"]).content, path)
            used.add(photo["id"])
            return {"type": "image", **dims, "credit": f"Photo: {photo.get('photographer', '')} / Pexels"}
    except Exception as exc:
        log(f"    Pexels photo failed: {exc}")
    return None


def nasa_image(query: str, path: str, used: set) -> dict | None:
    if not query:
        return None
    try:
        res = _get("https://images-api.nasa.gov/search",
                   params={"q": query, "media_type": "image", "page_size": 25}).json()
        for item in res.get("collection", {}).get("items", []):
            meta = (item.get("data") or [{}])[0]
            nasa_id = meta.get("nasa_id")
            if not nasa_id or nasa_id in used:
                continue
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
            return {"type": "image", **dims, "credit": f"Image: NASA{' ' + center if center else ''}"}
    except Exception as exc:
        log(f"    NASA search failed: {exc}")
    return None


def ai_image(prompt: str, path: str) -> dict | None:
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not (account and token and prompt):
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    try:
        resp = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                             json={"prompt": prompt + AI_STYLE, "steps": 8, "seed": random.randint(1, 10**6)},
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
def gather(script: dict, run_dir: str) -> list:
    """Return one media description per scene; files are saved in run_dir."""
    used: set = set()
    out = []
    space = script["category"] in {"space", "science"}
    for i, sc in enumerate(script["scenes"]):
        vis = sc["visual"]
        footage = vis.get("footage") or vis.get("query") or ""
        prompt = vis.get("ai_prompt") or ""
        nasa_q = vis.get("nasa") or (footage if space else "")
        base = os.path.join(run_dir, f"scene{i + 1}")
        steps = []
        if space and nasa_q:
            steps.append(("NASA", lambda: nasa_image(nasa_q, base + ".jpg", used)))
        steps += [
            ("Pexels video", lambda: pexels_video(footage, base + ".mp4", used)),
            ("AI image", lambda: ai_image(prompt, base + ".jpg")),
            ("Pexels photo", lambda: pexels_photo(footage, base + ".jpg", used)),
            ("NASA", lambda: nasa_image(nasa_q or footage, base + ".jpg", used)),
        ]
        media = None
        for name, step in steps:
            media = step()
            if media:
                log(f"  scene {i + 1}: {name} ({footage or prompt[:40]})")
                break
        if not media:
            log(f"  scene {i + 1}: plain background")
            media = plain_background(base + ".jpg", i)
        ext = ".mp4" if media["type"] == "video" else ".jpg"
        media["src"] = f"run/scene{i + 1}{ext}"
        out.append(media)
    return out
