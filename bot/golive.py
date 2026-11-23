"""After a Short is published: wait until it goes live, then post its discussion question as a comment.

  python -m bot.golive wait     --meta output/ig.json   (sleeps until the publishing time, at most ~5.5 hours)
  python -m bot.golive comment  --meta output/ig.json
"""
import argparse
import datetime as dt
import json
import time

from . import youtube
from .util import log

MAX_WAIT = dt.timedelta(hours=5, minutes=40)


def wait(meta: dict) -> None:
    when = meta.get("publish_at")
    if not when:
        return
    left = dt.datetime.fromisoformat(when.replace("Z", "+00:00")) - dt.datetime.now(dt.timezone.utc)
    if dt.timedelta(0) < left <= MAX_WAIT:
        log(f"Waiting until {when} UTC, when the Short goes live...")
        time.sleep(left.total_seconds() + 60)


def comment(meta: dict) -> None:
    question, vid = (meta.get("question") or "").strip(), meta.get("video_id")
    if not question or not vid:
        log("No question or no video: nothing to comment.")
        return
    if "https://www.googleapis.com/auth/youtube.force-ssl" not in youtube.granted_scopes():
        log("Comment skipped: the YouTube token does not have the permission to comment yet.")
        return
    yt = youtube.service()
    for attempt in range(4):
        try:
            cid = youtube.comment(yt, vid, question)
            log(f"Comment posted under https://youtube.com/shorts/{vid}: {question} ({cid})")
            return
        except Exception as exc:
            log(f"  comment attempt {attempt + 1} failed: {str(exc)[:200]}")
            time.sleep(120)
    log("Comment not posted (YouTube kept refusing); the video itself is fine.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["wait", "comment"])
    ap.add_argument("--meta", default="output/ig.json")
    args = ap.parse_args()
    meta = json.loads(open(args.meta, encoding="utf-8").read())
    if args.step == "wait":
        wait(meta)
    else:
        comment(meta)
