"""Publish every Short also as an Instagram Reel (Instagram API with Instagram Login).

Secrets (GitHub → Settings → Secrets and variables → Actions):
  IG_ACCESS_TOKEN  the token from Meta's App Dashboard (Instagram > API setup with Instagram login)
  IG_APP_SECRET    the "Instagram app secret" from the same page

The token lasts 60 days. The bot renews it automatically every week and keeps the renewed one in
data/ig_token.enc, encrypted with IG_APP_SECRET (the repository is public: never store it in clear).

Instagram downloads the video from a public link, so the workflow first puts the file on the
ig-media branch (raw.githubusercontent.com) and passes that link here.

  python -m bot.instagram check                          → which account, does the token work
  python -m bot.instagram post --meta output/ig.json --url <public mp4 link>
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import requests

from .util import DATA, log

API = "https://graph.instagram.com/v25.0"
STORE = DATA / "ig_token.enc"
HISTORY = DATA / "ig_history.json"
REFRESH_EVERY = dt.timedelta(days=7)
MAX_WAIT = dt.timedelta(hours=5, minutes=40)


def _clean(value: str) -> str:
    parts = [p.strip('"\'\\,;') for p in (value or "").split()]
    parts = [p for p in parts if p and p.lower() not in {"bearer", "authorization:", "curl", "-h"}]
    keyish = [p for p in parts if re.fullmatch(r"[A-Za-z0-9_\-|.]{20,}", p)]
    return (keyish or parts or [""])[0]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _fernet():
    secret = _clean(os.environ.get("IG_APP_SECRET", ""))
    if not secret:
        return None
    from cryptography.fernet import Fernet
    key = hashlib.sha256(b"world-in-a-shot/instagram:" + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _load_saved() -> dict | None:
    f = _fernet()
    if not f or not STORE.exists():
        return None
    try:
        return json.loads(f.decrypt(STORE.read_bytes()))
    except Exception:
        return None


def _save(token: str) -> None:
    f = _fernet()
    if not f:
        log("  note: IG_APP_SECRET is missing, so the renewed token cannot be saved")
        return
    STORE.write_bytes(f.encrypt(json.dumps({"token": token, "refreshed": _now().isoformat()}).encode()))


def _me(token: str) -> dict | None:
    try:
        r = requests.get(f"{API}/me", params={"fields": "user_id,username", "access_token": token}, timeout=30)
        return r.json() if r.ok else None
    except requests.RequestException:
        return None


def _refresh(token: str) -> str | None:
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
        return r.json().get("access_token") if r.ok else None
    except requests.RequestException:
        return None


def get_token(renew: bool = True) -> tuple[str, dict]:
    """A working token (renewed when it is a week old) and the account it belongs to."""
    candidates = []
    saved = _load_saved()
    if saved and saved.get("token"):
        candidates.append((saved["token"], saved.get("refreshed")))
    secret = _clean(os.environ.get("IG_ACCESS_TOKEN", ""))
    if secret:
        candidates.append((secret, None))
    for token, refreshed in candidates:
        me = _me(token)
        if not me:
            continue
        old = refreshed is None or _now() - dt.datetime.fromisoformat(refreshed) > REFRESH_EVERY
        if renew and old:
            new = _refresh(token)
            if new:
                token = new
                _save(token)
                log("  Instagram token renewed for another 60 days")
        return token, me
    sys.exit("Instagram: no working access token. Make a new one in Meta's App Dashboard "
             "(Instagram > API setup with Instagram login > Generate token) and save it as IG_ACCESS_TOKEN.")


def caption_for(title: str, summary: str, sources: list, tags: list) -> str:
    ig_tags = [t for t in tags if t.lower() != "#shorts"]
    for extra in ("#news", "#worldnews"):
        if extra not in [t.lower() for t in ig_tags]:
            ig_tags.append(extra)
    text = (f"{title}\n\n{summary}\n\nSources: {', '.join(sources)}\nNarrated with an AI voice.\n\n"
            + " ".join(ig_tags[:5]))  # Instagram allows at most 5 hashtags
    return text[:2200]


def publish(token: str, video_url: str, caption: str) -> tuple[str, str]:
    r = requests.post(f"{API}/me/media", timeout=60, data={
        "media_type": "REELS", "video_url": video_url, "caption": caption,
        "share_to_feed": "true", "access_token": token})
    if not r.ok:
        raise RuntimeError(f"Instagram refused the Reel: {r.text[:600]}")
    container = r.json()["id"]
    for _ in range(90):  # Instagram downloads and processes the video: up to 15 minutes
        time.sleep(10)
        st = requests.get(f"{API}/{container}", timeout=30,
                          params={"fields": "status_code,status", "access_token": token}).json()
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {st}")
    else:
        raise RuntimeError("Instagram was still processing the video after 15 minutes")
    r = requests.post(f"{API}/me/media_publish", timeout=60,
                      data={"creation_id": container, "access_token": token})
    if not r.ok:
        raise RuntimeError(f"Instagram did not publish the Reel: {r.text[:600]}")
    media_id = r.json()["id"]
    link = requests.get(f"{API}/{media_id}", timeout=30,
                        params={"fields": "permalink", "access_token": token}).json().get("permalink", "")
    return media_id, link


def post(meta_path: str, url: str) -> None:
    meta = json.loads(open(meta_path, encoding="utf-8").read())
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    slot = meta.get("slot")
    if slot and any(h.get("slot") == slot for h in history):
        log(f"The Reel for {slot} is already on Instagram: nothing to do.")
        return
    when = meta.get("publish_at")
    if when:
        wait = dt.datetime.fromisoformat(when.replace("Z", "+00:00")) - _now()
        if dt.timedelta(0) < wait <= MAX_WAIT:
            log(f"Waiting until {when} UTC to publish at the same time as YouTube…")
            time.sleep(wait.total_seconds())
        elif wait > MAX_WAIT:
            log("The slot is too far away to wait: publishing the Reel now.")
    token, me = get_token()
    log(f"Publishing the Reel on @{me.get('username')}…")
    media_id, link = publish(token, url, meta["caption"])
    log(f"  done: {link}")
    history.append({"date": _now().isoformat(timespec="minutes"), "slot": slot, "title": meta.get("title"),
                    "media_id": media_id, "permalink": link, "youtube": meta.get("video_id")})
    HISTORY.write_text(json.dumps(history[-300:], indent=1, ensure_ascii=False))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(f"### 📸 Instagram Reel: {meta.get('title')}\n- {link}\n")


def check() -> None:
    if not os.environ.get("IG_ACCESS_TOKEN", "").strip() and not STORE.exists():
        print("INSTAGRAM: NOT SET UP (add the IG_ACCESS_TOKEN secret)")
        return
    token, me = get_token(renew=False)
    print(f"INSTAGRAM: OK @{me.get('username')} (account {me.get('user_id')})")
    if not os.environ.get("IG_APP_SECRET", "").strip():
        print("INSTAGRAM: add the IG_APP_SECRET secret too, otherwise the token cannot be renewed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["post", "check"])
    ap.add_argument("--meta", default="output/ig.json")
    ap.add_argument("--url", default="")
    args = ap.parse_args()
    if args.step == "check":
        check()
    else:
        post(args.meta, args.url)
