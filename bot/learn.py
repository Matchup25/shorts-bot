"""Learning from our own results.

Every time the bot makes a Short it first reads the numbers of the videos it already published:
- YouTube views, likes and comments at fixed ages (1 day, 2 days, 7 days), so videos can be compared fairly;
- how much of each video people watch (needs the yt-analytics.readonly permission; skipped otherwise);
- Instagram likes and comments of the Reels.
When there are enough videos it asks Gemini to turn the numbers into a short "playbook" (data/playbook.md):
which kinds of stories, titles and hooks work for THIS channel. The playbook is then given to the editor
and the writer as advice — never above the rules on truth and neutrality.
"""
import datetime as dt
import json

from . import youtube
from .util import DATA, log

PLAYBOOK = DATA / "playbook.md"
BUCKETS = [("1d", 1), ("2d", 2), ("7d", 7)]
MIN_VIDEOS = 6          # videos with 2-day numbers needed before writing a playbook
REFRESH_DAYS = 6        # rewrite the playbook about once a week


def _age_days(entry: dict, now: dt.datetime) -> float:
    when = entry.get("publish_at") or entry.get("date")
    try:
        t = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return -1
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (now - t).total_seconds() / 86400


def update_stats(yt, history: list) -> int:
    """Store views/likes/comments at 1, 2 and 7 days (and the latest) in each history entry."""
    now = dt.datetime.now(dt.timezone.utc)
    recent = [h for h in history if h.get("video_id") and 0 <= _age_days(h, now) <= 30]
    if not recent:
        return 0
    numbers = {}
    for i in range(0, len(recent), 50):
        ids = ",".join(h["video_id"] for h in recent[i:i + 50])
        try:
            res = yt.videos().list(part="statistics", id=ids).execute()
        except Exception as exc:
            log(f"  could not read video numbers: {exc}")
            return 0
        for item in res.get("items", []):
            st = item.get("statistics", {})
            numbers[item["id"]] = {k: int(st.get(f"{k}Count", 0)) for k in ("view", "like", "comment")}
    for h in recent:
        n = numbers.get(h["video_id"])
        if not n:
            continue
        age = _age_days(h, now)
        stats = h.setdefault("stats", {})
        stats["latest"] = {**n, "age_days": round(age, 2)}
        for name, days in BUCKETS:  # only when seen at about that age, so videos compare fairly
            if days <= age < days + 1 and name not in stats:
                stats[name] = n
    ids = [h["video_id"] for h in recent]
    start = min(str(h.get("publish_at") or h.get("date"))[:10] for h in recent)
    ret = youtube.analytics_retention(ids, start, now.date().isoformat())
    for h in recent:
        if h["video_id"] in ret:
            h["retention"] = ret[h["video_id"]]
    log(f"  numbers updated for {len(numbers)} videos" + (f", watch-time for {len(ret)}" if ret else ""))
    return len(numbers)


def instagram_stats() -> None:
    """Likes and comments of our Reels (stored in data/ig_history.json)."""
    path = DATA / "ig_history.json"
    if not path.exists():
        return
    try:
        from . import instagram
        hist = json.loads(path.read_text())
        token, acc = instagram.get_token(renew=False)
    except SystemExit:
        return
    except Exception as exc:
        log(f"  Instagram numbers skipped: {exc}")
        return
    for h in hist[-60:]:
        if not h.get("media_id"):
            continue
        try:
            r = instagram._call("GET", f"{acc['api']}/{h['media_id']}", token, fields="like_count,comments_count")
            if r.ok:
                d = r.json()
                h["stats"] = {"likes": d.get("like_count"), "comments": d.get("comments_count"),
                              "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
        except Exception:
            continue
    path.write_text(json.dumps(hist, indent=1, ensure_ascii=False))


def _table(history: list) -> list:
    ig = {}
    try:
        for h in json.loads((DATA / "ig_history.json").read_text()):
            if h.get("youtube") and h.get("stats"):
                ig[h["youtube"]] = h["stats"]
    except Exception:
        pass
    rows = []
    for h in history:
        two = (h.get("stats") or {}).get("2d")
        if not two:
            continue
        rows.append({
            "title": h.get("title"), "category": h.get("category"), "hook": h.get("hook"),
            "seconds": h.get("seconds"), "slot_utc": (h.get("slot") or "")[11:16],
            "youtube_demand_views": (h.get("demand") or {}).get("views"),
            "views_2d": two["view"], "likes_2d": two["like"], "comments_2d": two["comment"],
            "views_7d": (h["stats"].get("7d") or {}).get("view"),
            "avg_pct_watched": (h.get("retention") or {}).get("avg_pct"),
            "ig_likes": (ig.get(h.get("video_id")) or {}).get("likes"),
        })
    return rows


def maybe_write_playbook(brain, history: list) -> bool:
    rows = _table(history)
    if len(rows) < MIN_VIDEOS:
        log(f"  playbook: {len(rows)}/{MIN_VIDEOS} videos with 2-day numbers, not enough yet")
        return False
    if PLAYBOOK.exists():
        text = PLAYBOOK.read_text()
        try:
            updated = dt.date.fromisoformat(text.split("Updated ", 1)[1][:10])
        except (IndexError, ValueError):
            updated = dt.date(2000, 1, 1)
        old_n = text.split("based on ", 1)[-1].split(" ", 1)[0]
        fresh = (dt.date.today() - updated).days < REFRESH_DAYS
        if fresh and old_n.isdigit() and len(rows) < int(old_n) + 5:
            return False
    rows.sort(key=lambda r: r["views_2d"], reverse=True)
    prompt = f"""You analyse the results of our YouTube Shorts news channel. Each row is one of our videos with its
numbers after 2 days (and 7 days when available), the share of the video people watched, Instagram likes, and how
much YouTube was watching the topic when we picked it.

{json.dumps(rows, ensure_ascii=False)}

Write at most 8 short, concrete rules that would help us choose stories and write titles and first sentences that
get more views ON THIS CHANNEL. Only state what the numbers really support; when the data is too thin for a point,
leave it out. Never suggest anything misleading, sensational beyond the facts, or one-sided on politics.
Return JSON: {{"rules": ["..."], "best_examples": ["<title of a top video>", "..."]}}"""
    try:
        res = brain.ask(prompt, temperature=0.2)
    except Exception as exc:
        log(f"  playbook not updated: {exc}")
        return False
    rules = [str(r).strip() for r in res.get("rules", []) if str(r).strip()][:8]
    if not rules:
        return False
    best = [str(t) for t in res.get("best_examples", [])][:3]
    text = (f"# What works on World in a Shot\n\nUpdated {dt.date.today().isoformat()}, based on {len(rows)} videos.\n\n"
            + "\n".join(f"- {r}" for r in rules)
            + ("\n\nBest so far: " + "; ".join(best) if best else "") + "\n")
    PLAYBOOK.write_text(text, encoding="utf-8")
    log("  playbook updated:\n" + text)
    return True


def playbook_text() -> str:
    """The rules, ready to paste into a prompt ('' while there is no playbook yet)."""
    if not PLAYBOOK.exists():
        return ""
    lines = [ln for ln in PLAYBOOK.read_text(encoding="utf-8").splitlines() if ln.startswith("- ") or ln.startswith("Best")]
    return "\n".join(lines)
