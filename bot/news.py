"""Agent 1 – the researcher: collects fresh stories from major news outlets."""
import calendar
import html
import re
import time

import feedparser
import requests

from .util import log

UA = "Mozilla/5.0 (compatible; ShortsNewsBot/1.0; +https://github.com)"
STOP = set("""a an the of to in on for and or but with from by at as is are was were be been it its this that these those
new news says said after over into up out about more than his her their they he she we you i not no yes how why what who
will can could would just first last one two three year years day week world""".split())


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _tokens(title: str) -> set:
    words = re.findall(r"[a-z0-9']+", title.lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def fetch_stories(cfg: dict) -> list:
    """Return a list of fresh stories: {id, title, summary, source, link, published}."""
    max_age = cfg.get("max_story_age_hours", 36) * 3600
    now = time.time()
    stories, seen_links = [], set()
    for source, urls in cfg["feeds"].items():
        for url in urls:
            try:
                resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
                feed = feedparser.parse(resp.content)
            except Exception as exc:  # network problems: skip this feed
                log(f"  feed skipped ({source}): {exc}")
                continue
            count = 0
            for entry in feed.entries[:40]:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                published = calendar.timegm(stamp) if stamp else None
                if published is None or now - published > max_age:
                    continue  # too old (or undated, e.g. a dead feed)
                title = _clean(entry.get("title", ""))
                if len(title) < 15 or "/live/" in link or "/video/" in link or "/av/" in link:
                    continue  # skip live blogs and video-only pages
                seen_links.add(link)
                stories.append({
                    "title": title,
                    "summary": _clean(entry.get("summary", ""))[:400],
                    "source": source,
                    "link": link,
                    "published": published,
                })
                count += 1
            log(f"  {source}: {count} fresh items from {url.split('/')[2]}")
    stories.sort(key=lambda s: s["published"], reverse=True)
    for i, story in enumerate(stories):
        story["id"] = i
    return stories


def related(story: dict, stories: list, limit: int = 3) -> list:
    """Find the same story reported by other outlets (simple word overlap)."""
    base = _tokens(story["title"] + " " + story["summary"])
    scored = []
    for other in stories:
        if other["link"] == story["link"] or other["source"] == story["source"]:
            continue
        toks = _tokens(other["title"] + " " + other["summary"])
        if not base or not toks:
            continue
        score = len(base & toks) / len(base | toks)
        if score >= 0.18:
            scored.append((score, other))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked, sources = [], set()
    for _, other in scored:
        if other["source"] not in sources:
            picked.append(other)
            sources.add(other["source"])
        if len(picked) >= limit:
            break
    return picked


def count_outlets(stories: list) -> None:
    """Add `outlets` = how many different outlets report each story."""
    for story in stories:
        story["outlets"] = 1 + len(related(story, stories, limit=6))


def article_text(url: str, fallback: str = "") -> str:
    """Download the article and keep only the main text."""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) if downloaded else None
        if text and len(text) > 300:
            return text[:7000]
    except Exception as exc:
        log(f"  could not read article ({exc}); using summary")
    return fallback
