"""The whole pipeline: news → story pick → script → fact-check → hashtags → voice → video → YouTube."""
import datetime as dt
import os
import sys

from . import assemble, media, news, render, voice, youtube
from .brain import Brain
from .util import OUTPUT, load_config, load_history, log, save_history


def next_slot(cfg: dict) -> str | None:
    """Next publishing time (07:00 / 19:00 Zurich…) as UTC RFC3339, at least 15 minutes from now."""
    from zoneinfo import ZoneInfo
    times = cfg.get("publish_times") or []
    if not times or os.environ.get("PRIVACY_OVERRIDE", "").strip():
        return None  # manual run with a chosen privacy: publish right away
    tz = ZoneInfo(cfg.get("timezone", "Europe/Zurich"))
    now = dt.datetime.now(tz)
    candidates = []
    for day in (0, 1):
        for hhmm in times:
            h, m = (int(x) for x in str(hhmm).split(":"))
            when = (now + dt.timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
            if when > now + dt.timedelta(minutes=15):
                candidates.append(when)
    slot = min(candidates)
    return slot.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summary(md: str) -> None:
    """Write a short report that appears on the GitHub run page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")


def main() -> None:
    cfg = load_config()
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    history = load_history()
    used_links = {link for h in history for link in h.get("links", [])}
    OUTPUT.mkdir(exist_ok=True)

    slot = next_slot(cfg) if cfg["privacy"] == "public" and not dry_run else None
    if slot and any(h.get("publish_at") == slot for h in history):
        log(f"A Short is already scheduled for {slot} (UTC): nothing to do.")
        summary(f"### ⏭️ A Short is already scheduled for {slot} UTC")
        return

    log("1/6 Reading the news…")
    stories = news.fetch_stories(cfg)
    stories = [s for s in stories if s["link"] not in used_links]
    if not stories:
        sys.exit("No fresh stories found in the feeds.")
    news.count_outlets(stories)
    log(f"  {len(stories)} fresh stories")

    brain = Brain(cfg)
    log("2/6 Choosing the best stories…")
    trends = youtube.google_trends()
    picks = brain.pick_stories(stories, history, trends)
    yt = None if dry_run and not os.environ.get("YT_REFRESH_TOKEN") else youtube.service()

    made = 0
    for story in picks:
        log(f"3/6 Writing: {story['title']}")
        sources = [story] + news.related(story, stories)
        for s in sources:
            s["text"] = news.article_text(s["link"], fallback=f"{s['title']}. {s['summary']}")
        script, feedback = None, ""
        for attempt in range(2):
            draft = brain.write_script(story, sources, feedback)
            check = brain.verify(draft, sources)
            if str(check.get("approved")).lower() in {"true", "yes", "1"}:
                script = draft
                break
            feedback = "\n".join(f"- {p}" for p in check.get("problems", []))
            log(f"  fact-check rejected draft {attempt + 1}:\n{feedback}")
        if not script:
            log("  skipping this story (could not pass the fact-check)")
            continue

        log("4/6 Finding trending hashtags…")
        candidates = youtube.popular_hashtags(yt, script["search_keywords"]) if yt else []
        tags = brain.choose_hashtags(script, candidates, trends)
        log(f"  {' '.join(tags)}")

        log("5/6 Pictures, voice and animation…")
        run_dir = render.reset_run_dir()
        media_list = media.gather(script, run_dir)
        audio, timings, words = voice.narrate(script["scenes"], cfg["voice"], cfg["voice_speed"])
        duration = assemble.build_mix(audio, timings, f"{run_dir}/mix.wav")
        source_names = list(dict.fromkeys(s["source"] for s in sources))
        props = assemble.build_props(script, timings, words, media_list, cfg["channel_name"], "run/mix.wav", duration)
        stamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M")
        out = str(OUTPUT / f"short_{stamp}_{made + 1}.mp4")
        render.render(props, out)

        credits = sorted({"Pixabay" if "Pixabay" in m.get("credit", "") else
                          "Pexels" if "Pexels" in m.get("credit", "") else
                          "NASA" if "NASA" in m.get("credit", "") else
                          "AI-generated images (FLUX)" if "AI" in m.get("credit", "") else ""
                          for m in media_list} - {""})
        description = (
            f"{script['description']}\n\n"
            "Sources:\n" + "\n".join(f"• {s['source']}: {s['link']}" for s in sources) + "\n\n"
            "Narration voice is AI-generated."
            + (" Visuals: " + "; ".join(credits) + "." if credits else "") + "\n\n" + " ".join(tags)
        )

        video_id = None
        publish_at = None
        if dry_run:
            log("6/6 Test mode: not uploading (download the video from the GitHub run page)")
        else:
            publish_at = next_slot(cfg) if cfg["privacy"] == "public" else None
            when = f"scheduled for {publish_at} (UTC)" if publish_at else cfg["privacy"]
            log(f"6/6 Uploading to YouTube, {when}…")
            video_id = youtube.upload(yt, out, script["title"], description, tags, script["category"],
                                      cfg["privacy"], cfg.get("ai_disclosure", True), publish_at)
            log(f"  done: https://youtube.com/shorts/{video_id}")
            history.append({
                "date": dt.datetime.utcnow().isoformat(timespec="minutes"),
                "title": script["title"],
                "links": [s["link"] for s in sources],
                "video_id": video_id,
                "publish_at": publish_at,
            })
            save_history(history)

        link = f"https://youtube.com/shorts/{video_id}" if video_id else "(test mode – see Artifacts below)"
        summary(f"### ✅ {script['title']}\n- Video: {link}\n- Privacy: {cfg['privacy']}"
                f"{' (goes live ' + publish_at + ' UTC)' if not dry_run and publish_at else ''}\n"
                f"- Hashtags: {' '.join(tags)}\n- Sources: {', '.join(source_names)}\n")
        made += 1
        if made >= int(cfg.get("videos_per_run", 1)):
            break

    if made == 0:
        sys.exit("No video was made today (no story passed the fact-check).")


if __name__ == "__main__":
    main()
