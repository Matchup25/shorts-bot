"""Build output/ig.json for a Short that is already on YouTube (used by instagram-repost.yml)."""
import glob
import json
import os
import re

from . import instagram, youtube
from .util import OUTPUT, log

if __name__ == "__main__":
    vid = os.environ["VIDEO_ID"].strip()
    yt = youtube.service()
    items = yt.videos().list(part="snippet", id=vid).execute().get("items", [])
    if not items:
        raise SystemExit(f"YouTube video {vid} not found")
    sn = items[0]["snippet"]
    desc = sn.get("description", "")
    summary = desc.split("\n\n")[0].strip()
    sources = re.findall(r"^• ([^:]+):", desc, flags=re.M)
    tags = re.findall(r"#\w+", desc.split("\n")[-1]) if desc else []
    videos = sorted(glob.glob(str(OUTPUT / "*.mp4")))
    if not videos:
        raise SystemExit("No video file in this run")
    when = os.environ.get("WHEN", "").strip() or None
    meta = {"title": sn["title"], "slot": f"youtube:{vid}", "publish_at": when, "video_id": vid,
            "video": os.path.basename(videos[0]),
            "caption": instagram.caption_for(sn["title"], summary, sources, tags)}
    (OUTPUT / "ig.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log("Caption:\n" + meta["caption"])
