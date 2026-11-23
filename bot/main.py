"""The whole pipeline: news → story pick → script → fact-check → hashtags → voice → video → YouTube."""
import datetime as dt
import json
import math
import os
import sys

from . import assemble, instagram, learn, media, news, render, slots, voice, youtube
from .brain import Brain
from .util import OUTPUT, load_config, load_history, log, save_history, DATA


def summary(md: str) -> None:
    """Write a short report that appears on the GitHub run page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")


def weekly_link(cfg: dict) -> str:
    """The latest Sunday show, or the channel's videos page until the first one is out."""
    try:
        hist = json.loads((DATA / "weekly_history.json").read_text())
        vid = [h for h in hist if h.get("video_id")][-1]["video_id"]
        return f"https://youtu.be/{vid}"
    except Exception:
        return f"https://www.youtube.com/{cfg.get('youtube_handle', '@shottheworld')}/videos"


def rank_by_demand(yt, picks: list) -> list:
    """Editor's order, corrected by how much people watch Shorts on each topic right now.
    One order of magnitude more views is worth moving up about 6 places."""
    log("  Measuring how much each topic is watched on YouTube right now…")
    for rank, story in enumerate(picks):
        story["editor_rank"] = rank + 1
        story["demand"] = youtube.shorts_demand(yt, story.get("yt_query") or story["title"])

    def score(story):
        d = story.get("demand")
        views = d["views"] if d else 0
        return math.log10(1 + views) - 0.15 * (story["editor_rank"] - 1)

    ranked = sorted(picks, key=score, reverse=True)
    for s in ranked:
        d = s.get("demand") or {}
        log(f"    #{s['editor_rank']} {score(s):5.2f}  views={d.get('views', '?'):>10}  q='{s.get('yt_query')}'  {s['title'][:60]}")
    return ranked


def main() -> None:
    cfg = load_config()
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    history = load_history()
    used_links = {link for h in history for link in h.get("links", [])}
    OUTPUT.mkdir(exist_ok=True)

    slot, publish_slot = None, None
    if slots.uses_slots(cfg):
        slot, publish_slot = slots.choose(cfg, history, slots.is_manual())
        if not slot:
            log("No Short is due right now (the next slot is far away or already filled).")
            summary("### ⏭️ No Short due right now")
            return
        log(f"Making the Short for slot {slot} UTC" + ("" if publish_slot else " (late: publishing right away)"))

    log("1/6 Reading the news…")
    stories = news.fetch_stories(cfg)
    stories = [s for s in stories if s["link"] not in used_links]
    if not stories:
        sys.exit("No fresh stories found in the feeds.")
    news.count_outlets(stories)
    log(f"  {len(stories)} fresh stories")

    brain = Brain(cfg)
    yt = None if dry_run and not os.environ.get("YT_REFRESH_TOKEN") else youtube.service()
    if yt:
        log("Learning from our earlier videos…")
        try:
            learn.update_stats(yt, history)
            learn.instagram_stats()
            learn.maybe_write_playbook(brain, history)
        except Exception as exc:  # learning must never stop a Short
            log(f"  learning step skipped: {exc}")
    log("2/6 Choosing the best stories…")
    trends = youtube.google_trends()
    picks = brain.pick_stories(stories, history, trends)
    if yt and picks:
        picks = rank_by_demand(yt, picks)
    force = os.environ.get("FORCE_STORY", "").strip().lower()
    if dry_run and force:  # test runs only: make a Short about a chosen story
        forced = [s for s in stories if force in s["title"].lower()]
        if forced:
            forced[0]["yt_query"] = forced[0]["title"]
            picks = forced[:1] + [p for p in picks if p is not forced[0]]
            log(f"  test: forcing the story '{forced[0]['title']}'")

    made = 0
    for story in picks:
        log(f"3/6 Writing: {story['title']}")
        sources = [story] + news.related(story, stories)
        for s in sources:
            s["text"] = news.article_text(s["link"], fallback=f"{s['title']}. {s['summary']}")
        script, feedback = None, ""
        for attempt in range(2):
            draft = brain.write_script(story, sources, feedback)
            check = brain.verify(draft, sources, story["title"])
            if str(check.get("approved")).lower() in {"true", "yes", "1"}:
                script = draft
                break
            feedback = "\n".join(f"- {p}" for p in check.get("problems", []))
            log(f"  fact-check rejected draft {attempt + 1}:\n{feedback}")
        if not script:
            log("  skipping this story (could not pass the fact-check)")
            continue
        # Title and hook contest; the winner must pass the fact-check again, otherwise the checked original stays.
        sharp = brain.sharpen(script, story.get("yt_query", ""), story["title"])
        if (sharp["title"], sharp["scenes"][0]["narration"]) != (script["title"], script["scenes"][0]["narration"]):
            check = brain.verify(sharp, sources, story["title"])
            if str(check.get("approved")).lower() in {"true", "yes", "1"}:
                script = sharp
                log("  the contest winner passed the fact-check")
            else:
                log("  contest winner rejected by the fact-check, keeping the original title and hook: "
                    + "; ".join(check.get("problems", [])))
                script["contest"] = sharp.get("contest")

        log("4/6 Finding trending hashtags…")
        candidates = youtube.popular_hashtags(yt, script["search_keywords"]) if yt else []
        tags = brain.choose_hashtags(script, candidates, trends)
        log(f"  {' '.join(tags)}")

        log("5/6 Pictures, voice and animation…")
        run_dir = render.reset_run_dir()
        media_list = media.gather(script, run_dir, second=True)
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
            + (f"💬 {script['question']}\n\n" if script.get("question") else "")
            + f"📺 The whole week in 15 stories, every Sunday 19:00 CET: {weekly_link(cfg)}\n\n"
            "Sources:\n" + "\n".join(f"• {s['source']}: {s['link']}" for s in sources) + "\n\n"
            "Narration voice is AI-generated."
            + (" Visuals: " + "; ".join(credits) + "." if credits else "") + "\n\n" + " ".join(tags)
        )

        video_id = None
        publish_at = None
        if dry_run:
            log("6/6 Test mode: not uploading (download the video from the GitHub run page)")
        else:
            publish_at = publish_slot if cfg["privacy"] == "public" else None
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
                "slot": slot,
                # what the bot decided, so it can learn later which choices bring views
                "category": script["category"],
                "hook": script["scenes"][0]["narration"],
                "words": sum(len(sc["narration"].split()) for sc in script["scenes"]),
                "seconds": round(duration, 1),
                "demand": story.get("demand"),
                "editor_rank": story.get("editor_rank"),
                "contest": script.get("contest"),
            })
            save_history(history)
            # The same video goes to Instagram as a Reel (a separate step, only if Instagram is set up).
            (OUTPUT / "ig.json").write_text(json.dumps({
                "title": script["title"], "slot": slot, "publish_at": publish_at, "video_id": video_id,
                "video": os.path.basename(out),
                "caption": instagram.caption_for(script["title"], script["description"], source_names, tags,
                                                 script.get("question", ""), cfg.get("youtube_handle", "")),
                "question": script.get("question", ""),
            }, ensure_ascii=False, indent=1), encoding="utf-8")

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
