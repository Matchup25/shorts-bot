"""Publish every Short also as an Instagram Reel.

Two kinds of Meta apps are supported (the bot finds out which one the token belongs to):
- "API setup with Unified login" (all new apps since autumn 2026): a system-user token that never
  expires, used on graph.facebook.com; the Instagram account is found with
  /me/assigned_instagram_accounts and the video is uploaded straight from the file.
- "API setup with Instagram login" (older apps): an Instagram user token valid 60 days, used on
  graph.instagram.com. The bot renews it every week and keeps the renewed one in data/ig_token.enc,
  encrypted with IG_APP_SECRET (the repository is public: never store a token in clear). Instagram
  then downloads the video from a public link (the ig-media branch).

Secrets (GitHub → Settings → Secrets and variables → Actions):
  IG_ACCESS_TOKEN  the token generated in Meta's App Dashboard
  IG_APP_SECRET    optional with Unified login; needed with Instagram login (to renew the token)

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

IG_API = "https://graph.instagram.com/v25.0"
FB_API = "https://graph.facebook.com/v25.0"
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


def _call(method: str, url: str, token: str, **params) -> requests.Response:
    """Graph API call; adds appsecret_proof when the app requires it."""
    params["access_token"] = token
    kw = {"params": params} if method == "GET" else {"data": params}
    r = requests.request(method, url, timeout=60, **kw)
    secret = _clean(os.environ.get("IG_APP_SECRET", ""))
    if not r.ok and "appsecret_proof" in r.text and secret:
        import hmac
        params["appsecret_proof"] = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        r = requests.request(method, url, timeout=60, **kw)
    return r


def _account(token: str) -> dict | None:
    """Which Instagram account the token can publish to, and through which API."""
    try:  # Unified login: system-user token on graph.facebook.com
        r = _call("GET", f"{FB_API}/me/assigned_instagram_accounts", token, fields="id,username")
        if not r.ok:
            r = _call("GET", f"{FB_API}/me/assigned_instagram_accounts", token)
        data = r.json().get("data") if r.ok else None
        if data:
            acc = data[0]
            return {"mode": "facebook", "api": FB_API, "ig_id": acc["id"],
                    "username": acc.get("username") or acc["id"], "all": [a.get("username") for a in data]}
    except (requests.RequestException, ValueError, KeyError):
        pass
    try:  # Instagram login: Instagram user token on graph.instagram.com
        r = requests.get(f"{IG_API}/me", params={"fields": "user_id,username", "access_token": token}, timeout=30)
        if r.ok:
            me = r.json()
            return {"mode": "instagram", "api": IG_API, "ig_id": "me", "username": me.get("username"),
                    "user_id": me.get("user_id")}
    except (requests.RequestException, ValueError):
        pass
    return None


def _refresh(token: str) -> str | None:
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
        return r.json().get("access_token") if r.ok else None
    except requests.RequestException:
        return None


def get_token(renew: bool = True) -> tuple[str, dict]:
    """A working token and the Instagram account it publishes to (Instagram-login tokens are renewed weekly)."""
    candidates = []
    saved = _load_saved()
    if saved and saved.get("token"):
        candidates.append((saved["token"], saved.get("refreshed")))
    secret = _clean(os.environ.get("IG_ACCESS_TOKEN", ""))
    if secret:
        candidates.append((secret, None))
    for token, refreshed in candidates:
        acc = _account(token)
        if not acc:
            continue
        if acc["mode"] == "instagram":
            old = refreshed is None or _now() - dt.datetime.fromisoformat(refreshed) > REFRESH_EVERY
            if renew and old:
                new = _refresh(token)
                if new:
                    token = new
                    _save(token)
                    log("  Instagram token renewed for another 60 days")
        return token, acc
    sys.exit("Instagram: no working access token, or the token cannot see any Instagram account. "
             "Generate a new one in Meta's App Dashboard and save it as IG_ACCESS_TOKEN.")


def caption_for(title: str, summary: str, sources: list, tags: list) -> str:
    ig_tags = [t for t in tags if t.lower() != "#shorts"]
    for extra in ("#news", "#worldnews"):
        if extra not in [t.lower() for t in ig_tags]:
            ig_tags.append(extra)
    text = (f"{title}\n\n{summary}\n\nSources: {', '.join(sources)}\nNarrated with an AI voice.\n\n"
            + " ".join(ig_tags[:5]))  # Instagram allows at most 5 hashtags
    return text[:2200]


def _wait_ready(api: str, token: str, container: str) -> None:
    for _ in range(90):  # Instagram processes the video: up to 15 minutes
        time.sleep(10)
        st = _call("GET", f"{api}/{container}", token, fields="status_code,status").json()
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {st}")
    raise RuntimeError("Instagram was still processing the video after 15 minutes")


def _container_upload(acc: dict, token: str, video_path: str, caption: str) -> str:
    """Unified/Facebook login: send the file itself (no public link needed)."""
    r = _call("POST", f"{acc['api']}/{acc['ig_id']}/media", token, media_type="REELS",
              upload_type="resumable", caption=caption, share_to_feed="true")
    if not r.ok:
        raise RuntimeError(f"Instagram refused the Reel: {r.text[:600]}")
    body = r.json()
    container = body["id"]
    uri = body.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v25.0/{container}"
    size = os.path.getsize(video_path)
    with open(video_path, "rb") as fh:
        up = requests.post(uri, data=fh, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if not up.ok:
        raise RuntimeError(f"Upload to Instagram failed: {up.text[:600]}")
    return container


def _container_link(acc: dict, token: str, video_url: str, caption: str) -> str:
    """Instagram downloads the video from a public link."""
    r = _call("POST", f"{acc['api']}/{acc['ig_id']}/media", token, media_type="REELS",
              video_url=video_url, caption=caption, share_to_feed="true")
    if not r.ok:
        raise RuntimeError(f"Instagram refused the Reel: {r.text[:600]}")
    return r.json()["id"]


def publish(token: str, acc: dict, video_path: str, video_url: str, caption: str) -> tuple[str, str]:
    container = None
    if acc["mode"] == "facebook" and video_path and os.path.exists(video_path):
        try:
            container = _container_upload(acc, token, video_path, caption)
            _wait_ready(acc["api"], token, container)
        except RuntimeError as exc:
            if not video_url:
                raise
            log(f"  direct upload did not work ({exc}); trying with the public link")
            container = None
    if container is None:
        if not video_url:
            raise RuntimeError("No public link for the video")
        container = _container_link(acc, token, video_url, caption)
        _wait_ready(acc["api"], token, container)
    r = _call("POST", f"{acc['api']}/{acc['ig_id']}/media_publish", token, creation_id=container)
    if not r.ok:
        raise RuntimeError(f"Instagram did not publish the Reel: {r.text[:600]}")
    media_id = r.json()["id"]
    link = _call("GET", f"{acc['api']}/{media_id}", token, fields="permalink").json().get("permalink", "")
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
    token, acc = get_token()
    log(f"Publishing the Reel on @{acc.get('username')} ({acc['mode']} login)…")
    video_path = os.path.join(os.path.dirname(os.path.abspath(meta_path)), meta.get("video", ""))
    media_id, link = publish(token, acc, video_path, url, meta["caption"])
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
    token, acc = get_token(renew=False)
    print(f"INSTAGRAM: OK @{acc.get('username')} ({acc['mode']} login, account {acc.get('ig_id')})")
    if acc["mode"] == "facebook" and len(acc.get("all") or []) > 1:
        print(f"INSTAGRAM: the token sees several accounts {acc['all']}; publishing to the first one")
    if acc["mode"] == "instagram" and not os.environ.get("IG_APP_SECRET", "").strip():
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
