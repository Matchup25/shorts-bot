"""Reference texts for the explainer channel (English Wikipedia, CC BY-SA).

The text is only used as the factual base: the script is written in our own words and the fact-check
compares every claim with it. Each video's description credits the articles used.
"""
import re

import requests

from .util import log

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "WorldInAShotBot/1.0 (https://github.com/Matchup25/shorts-bot)"}


def _extract(title: str) -> dict | None:
    r = requests.get(API, headers=HEADERS, timeout=30, params={
        "action": "query", "prop": "extracts|info", "explaintext": 1, "redirects": 1, "inprop": "url",
        "titles": title, "format": "json", "formatversion": 2})
    pages = r.json().get("query", {}).get("pages", []) if r.ok else []
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    text = re.sub(r"\n==+ *(See also|References|Further reading|External links|Notes|Bibliography) *==+.*", "",
                  page.get("extract", ""), flags=re.S)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 400:
        return None
    return {"source": "Wikipedia", "title": page["title"], "link": page.get("fullurl", ""), "text": text[:12000]}


STOP = {"how", "a", "an", "the", "is", "are", "does", "do", "work", "works", "really", "made", "why", "what"}


def search(query: str, limit: int = 3) -> list:
    words = [w for w in re.findall(r"[A-Za-z0-9'-]+", query) if w.lower() not in STOP]
    try:
        r = requests.get(API, headers=HEADERS, timeout=30, params={
            "action": "query", "list": "search", "srsearch": " ".join(words) or query, "srlimit": limit,
            "format": "json"})
        return [h["title"] for h in r.json().get("query", {}).get("search", [])] if r.ok else []
    except (requests.RequestException, ValueError) as exc:
        log(f"  encyclopedia search failed: {exc}")
        return []


def sources_for(topic: str, wiki_title: str = "") -> list:
    """One or two encyclopedia articles about the topic."""
    titles = ([wiki_title] if wiki_title else []) + search(topic)
    out, seen = [], set()
    for t in titles:
        if not t or t in seen:
            continue
        seen.add(t)
        try:
            art = _extract(t)
        except requests.RequestException:
            art = None
        if art and art["title"] not in {a["title"] for a in out}:
            out.append(art)
        if len(out) >= 2:
            break
    log(f"  sources: {', '.join(a['title'] for a in out) or 'none'}")
    return out
