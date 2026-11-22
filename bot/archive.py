"""Keeps a rolling 8-day archive of news stories (used by the weekly show).

Run:  python -m bot.archive
"""
import json
import time

from . import news
from .util import DATA, load_config, log

PATH = DATA / "archive.json"
KEEP_DAYS = 8


def load() -> list:
    if not PATH.exists():
        return []
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def collect() -> int:
    cfg = load_config()
    cfg["max_story_age_hours"] = 24 * 7
    stories = load()
    known = {s["link"] for s in stories}
    added = 0
    for s in news.fetch_stories(cfg):
        if s["link"] in known:
            continue
        stories.append({k: s[k] for k in ("title", "summary", "source", "link", "published")})
        known.add(s["link"])
        added += 1
    cutoff = time.time() - KEEP_DAYS * 86400
    stories = sorted((s for s in stories if s["published"] >= cutoff), key=lambda s: s["published"], reverse=True)
    DATA.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(stories, ensure_ascii=False, indent=0), encoding="utf-8")
    log(f"archive: +{added} new, {len(stories)} stories kept")
    return added


if __name__ == "__main__":
    collect()
