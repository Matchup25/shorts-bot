"""World in a Shot Weekly: the most important stories of the week in ~15 minutes, every Sunday at 19:00 Zurich.

  python -m bot.weekly prepare [--count 15] [--test]   # news, scripts, fact-check, voice, pictures, props
  python -m bot.weekly publish --video weekly.mp4 [--test]
The video itself is rendered in parallel by the workflow (.github/workflows/weekly-show.yml).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

from . import archive, assemble, media, news, render, voice, youtube
from .brain import Brain
from .util import DATA, load_config, log

RUN = render.RUN_DIR
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
FULL_MONTHS = ("January February March April May June July August September October November December").split()


def _labels(now: dt.datetime) -> tuple:
    start, end = (now - dt.timedelta(days=6)).date(), now.date()
    if start.month == end.month:
        short = f"{MONTHS[start.month - 1]} {start.day} – {end.day}, {end.year}"
        spoken = f"{FULL_MONTHS[start.month - 1]} {start.day} to {end.day}"
    else:
        short = f"{MONTHS[start.month - 1]} {start.day} – {MONTHS[end.month - 1]} {end.day}, {end.year}"
        spoken = f"{FULL_MONTHS[start.month - 1]} {start.day} to {FULL_MONTHS[end.month - 1]} {end.day}"
    return short, spoken


def _sunday_slot(cfg: dict, now: dt.datetime) -> str:
    h, m = (int(x) for x in str(cfg.get("weekly_publish_time", "19:00")).split(":"))
    days = (6 - now.weekday()) % 7
    slot = (now + dt.timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)
    if slot < now + dt.timedelta(minutes=30):
        slot += dt.timedelta(days=7)
    return slot.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _story_pool(cfg: dict) -> list:
    cfg7 = dict(cfg, max_story_age_hours=24 * 7)
    pool = {s["link"]: s for s in archive.load()}
    for s in news.fetch_stories(cfg7):
        pool.setdefault(s["link"], {k: s[k] for k in ("title", "summary", "source", "link", "published")})
    stories = list(pool.values())
    news.count_outlets(stories)
    stories.sort(key=lambda s: (-s["outlets"], -s["published"]))
    for i, s in enumerate(stories):
        s["id"] = i
    log(f"  {len(stories)} stories this week")
    return stories


def _ts(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else \
        f"{seconds // 60}:{seconds % 60:02d}"


def prepare(count: int, test: bool) -> None:
    cfg = load_config()
    media.ORIENTATION["value"] = "landscape"
    tz = ZoneInfo(cfg.get("timezone", "Europe/Zurich"))
    now = dt.datetime.now(tz)
    date_short, date_spoken = _labels(now)

    log("1/5 Collecting the week's news…")
    pool = _story_pool(cfg)
    brain = Brain(cfg)
    log("2/5 Choosing the most important stories…")
    picks = brain.pick_weekly(pool, count + 6, date_short)

    log("3/5 Writing and fact-checking each story…")
    accepted = []
    for story in picks:
        if len(accepted) >= count:
            break
        sources = [story] + news.related(story, pool)
        for s in sources:
            s["text"] = news.article_text(s["link"], fallback=f"{s['title']}. {s['summary']}")
        seg, feedback = None, ""
        for attempt in range(2):
            try:
                draft = brain.write_segment(story, sources, feedback)
            except Exception as exc:
                log(f"  could not write '{story['title'][:60]}': {exc}")
                break
            check = brain.verify(draft, sources)
            if str(check.get("approved")).lower() in {"true", "yes", "1"}:
                seg = draft
                break
            feedback = "\n".join(f"- {p}" for p in check.get("problems", []))
            log(f"  fact-check rejected '{draft['headline']}' (try {attempt + 1})")
        if not seg:
            continue
        seg["place"] = story["place"]
        seg["sources"] = [{"source": s["source"], "link": s["link"]} for s in sources]
        accepted.append(seg)
        log(f"  ✓ {len(accepted)}/{count}: {seg['headline']} ({story['place']['label']})")
    if len(accepted) < max(3, count // 2):
        sys.exit("Not enough stories passed the fact-check this week.")

    n = len(accepted)
    for i, seg in enumerate(accepted):
        seg["rank"] = i + 1  # 1 = most important
    show = list(reversed(accepted))  # countdown: n … 1

    log("4/5 Voice, pictures and sound…")
    intro = (f"This is World in a Shot Weekly. The {n} stories that shaped the week of {date_spoken}. "
             "Let's count them down.")
    outro = (f"That was the week in {n} stories. Subscribe for a new short every day, "
             "and we'll see you next Sunday.")
    narration = [{"narration": intro}] + [sc for seg in show for sc in seg["scenes"]] + [{"narration": outro}]
    audio, timings, words = voice.narrate(narration, cfg["voice"], cfg["voice_speed"])

    render.reset_run_dir()
    used: set = set()
    segments, whoosh, idx = [], [], 1
    for si, seg in enumerate(show):
        k = len(seg["scenes"])
        tms = timings[idx: idx + k]
        idx += k
        pics = media.gather({"category": seg["category"], "scenes": seg["scenes"]}, str(RUN),
                            prefix=f"s{si + 1}_", used=used, editorial=True,
                            place=seg["place"], allow_plain=False)
        scenes = []
        for j, (sc, tm, md) in enumerate(zip(seg["scenes"], tms, pics)):
            kind = sc["visual"]["kind"] if md else "map"
            entry = {"start": round(tm["start"], 3), "end": round(tm["end"], 3), "kind": kind,
                     "transition": assemble.TRANSITIONS[(si + j) % len(assemble.TRANSITIONS)]}
            if md:
                entry["media"] = md
            if kind == "stat":
                entry["stat"] = {"value": str(sc["visual"].get("value", "")), "unit": str(sc["visual"].get("unit", ""))}
            scenes.append(entry)
        segments.append({"rank": seg["rank"], "start": round(tms[0]["start"], 3), "end": round(tms[-1]["end"], 3),
                         "headline": seg["headline"], "category": seg["category"], "place": seg["place"],
                         "scenes": scenes})
        whoosh.append(tms[0]["start"])
    duration = assemble.build_mix(audio, timings, str(RUN / "mix.wav"), whoosh_at=whoosh)
    props = {
        "channel": cfg["channel_name"], "dateRange": date_short, "storyCount": n, "audio": "run/mix.wav",
        "duration": round(duration, 3),
        "intro": {"start": round(timings[0]["start"], 3), "end": round(timings[0]["end"], 3)},
        "outro": {"start": round(timings[-1]["start"], 3), "end": round(timings[-1]["end"], 3)},
        "segments": segments,
        "words": [{"text": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
                  for scene_words in words for w in scene_words],
    }
    (RUN / "weekly-props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    # thumbnail background: first picture of story #1
    top = next(s for s in segments if s["rank"] == 1)
    thumb_bg = None
    for sc in top["scenes"]:
        md = sc.get("media")
        if not md:
            continue
        src = str(RUN.parent / md["src"])
        if md["type"] == "video":
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", src, "-frames:v", "1",
                            str(RUN / "thumb_bg.jpg")], check=False)
            thumb_bg = "run/thumb_bg.jpg" if (RUN / "thumb_bg.jpg").exists() else None
        else:
            thumb_bg = md["src"]
        if thumb_bg:
            break
    thumb = {"dateRange": date_short, "storyCount": n, "topHeadline": top["headline"], "place": top["place"]}
    if thumb_bg:
        thumb["image"] = thumb_bg
    (RUN / "thumb-props.json").write_text(json.dumps(thumb, ensure_ascii=False), encoding="utf-8")

    log("5/5 Title, chapters and sources…")
    chapters = ["0:00 Intro"] + [f"{_ts(s['start'])} #{s['rank']} {s['headline']}" for s in segments] + \
        [f"{_ts(timings[-1]['start'])} That was the week"]
    by_rank = {s["rank"]: s for s in show}
    source_lines = []
    for s in segments:
        src = by_rank[s["rank"]]["sources"][0]
        source_lines.append(f"#{s['rank']} {s['headline']} — {src['source']}: {src['link']}")
    description = (
        f"The {n} most important stories of the week ({date_short}), explained in about {max(1, round(duration / 60))} minutes. "
        "Neutral, fact-checked against the original reporting, every Sunday.\n\n"
        "Chapters:\n" + "\n".join(chapters) + "\n\nSources:\n" + "\n".join(source_lines) + "\n\n"
        "Narration and illustrations are AI-generated; footage from Pixabay/Pexels/NASA. "
        "Subscribe for a new Short every day.\n\n#news #worldnews #weeklynews #worldinashot"
    )
    title = f"The {n} Stories That Shaped the Week | {date_short} | World in a Shot Weekly"
    meta = {
        "title": title[:100],
        "description": description[:4900],
        "tags": ["news", "world news", "weekly news", "news recap", "world in a shot"],
        "publish_at": None if test else _sunday_slot(cfg, now),
        "frames": int(duration * 30) + 1,
    }
    (RUN / "weekly-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  ready: {n} stories, {duration / 60:.1f} minutes, {meta['frames']} frames")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"frames={meta['frames']}\n")


def publish(video: str, test: bool) -> None:
    meta = json.loads((RUN / "weekly-meta.json").read_text(encoding="utf-8"))
    if test:
        log("Test mode: the weekly show is NOT uploaded.")
        return
    cfg = load_config()
    publish_at = meta.get("publish_at")
    if publish_at:
        when = dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        if when < dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10):
            publish_at = None  # running late: publish right away
    yt = youtube.service()
    vid = youtube.upload(yt, video, meta["title"], meta["description"], meta["tags"], "world", "public",
                         cfg.get("ai_disclosure", True), publish_at)
    log(f"  uploaded: https://youtube.com/watch?v={vid} (goes live {publish_at or 'now'})")
    thumb = RUN / "thumb.jpg"
    if thumb.exists():
        try:
            from googleapiclient.http import MediaFileUpload
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
            log("  custom thumbnail set")
        except Exception as exc:
            log(f"  thumbnail not set (verify the channel at youtube.com/verify to allow it): {exc}")
    hist_path = DATA / "weekly_history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    hist.append({"date": dt.date.today().isoformat(), "title": meta["title"], "video_id": vid,
                 "publish_at": publish_at})
    hist_path.write_text(json.dumps(hist[-100:], indent=1, ensure_ascii=False))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(f"### ✅ {meta['title']}\n- https://youtube.com/watch?v={vid}\n- goes live: {publish_at or 'now'}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "publish"])
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--video", default="weekly.mp4")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    if args.step == "prepare":
        prepare(args.count or int(load_config().get("weekly_stories", 15)), args.test)
    else:
        publish(args.video, args.test)
