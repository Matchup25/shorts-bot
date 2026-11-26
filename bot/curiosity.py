"""World Explained: one extra Short a day (21:00 Zurich) that teaches an evergreen curiosity about the world
(odd borders, enclaves, why a territory belongs to a country, flags, time zones...).

Same channel and the same safeguards as the news Shorts: facts only from encyclopedia articles (research.py),
strict fact-check, neutral wording; plus a globe that turns to the place. Also posted as an Instagram Reel.
Settings: config.yaml -> curiosity. Optional list of topics to do first: curiosity_topics.txt (one per line).

  python -m bot.curiosity --check   (is a video due? writes due=true/false)
  python -m bot.curiosity           (DRY_RUN=true: make the video but do not upload)
"""
import datetime as dt
import json
import os
import re
import sys

from . import slots
from .util import DATA, OUTPUT, ROOT, load_config, log

HISTORY = DATA / "curiosity_history.json"
TOPICS = ROOT / "curiosity_topics.txt"


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _overlap(a: str, b: str) -> float:
    """Share of words two sentences have in common (0-1)."""
    wa, wb = set(_norm(a).split()), set(_norm(b).split())
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def load_history() -> list:
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def _slot_cfg(cfg: dict) -> dict:
    return {**cfg, "publish_times": (cfg.get("curiosity") or {}).get("publish_times") or []}


def summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")


def due_check() -> None:
    cfg = load_config()
    test = os.environ.get("DRY_RUN", "").lower() == "true"
    cur = cfg.get("curiosity") or {}
    enabled = cur.get("enabled", True) and dt.date.today().isoformat() >= str(cur.get("start_date", "2000-01-01"))
    slot_cfg = _slot_cfg(cfg)
    due = test or (enabled and slots.uses_slots(slot_cfg)
                   and bool(slots.choose(slot_cfg, load_history(), slots.is_manual())[0]))
    log(f"World Explained video due: {due}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"due={'true' if due else 'false'}\n")


def listed_topics() -> list:
    if not TOPICS.exists():
        return []
    return [ln.strip() for ln in TOPICS.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def candidates(brain, history: list, yt) -> list:
    """Topics to try, best first: the list file in order, otherwise proposals ranked by YouTube interest."""
    from . import youtube
    done = {_norm(h["topic"]) for h in history}
    mine = [{"topic": t, "wikipedia": "", "query": t} for t in listed_topics() if _norm(t) not in done]
    if mine:
        return mine[:3]
    ideas = [t for t in brain.curiosity_topics([h["topic"] for h in history]) if _norm(t["topic"]) not in done]
    if yt:
        for t in ideas:
            d = youtube.shorts_demand(yt, t.get("query") or t["topic"], hours=24 * 90)
            t["demand"] = d["views"] if d else 0
        ideas.sort(key=lambda t: t.get("demand", 0), reverse=True)
        for t in ideas:
            log(f"    {t.get('demand', 0):>10} views  {t['topic']}")
    return ideas[:4]


def main() -> None:
    from . import assemble, instagram, media, polish, render, research, voice, youtube
    from .brain import Brain
    from .main import pick_voice

    cfg = load_config()
    cur = cfg.get("curiosity") or {}
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    history = load_history()
    OUTPUT.mkdir(exist_ok=True)
    slot, publish_slot = None, None
    if slots.uses_slots(_slot_cfg(cfg)):
        slot, publish_slot = slots.choose(_slot_cfg(cfg), history, slots.is_manual())
        if not slot:
            log("No World Explained video is due right now.")
            return
        log(f"Making the World Explained video for slot {slot} UTC")

    brain = Brain(cfg)
    yt = youtube.service()
    forced = os.environ.get("FORCE_TOPIC", "").strip()
    picks = [{"topic": forced, "wikipedia": "", "query": forced}] if forced else candidates(brain, history, yt)

    for pick in picks:
        topic = pick["topic"]
        log(f"Topic: {topic}")
        sources = research.sources_for(topic, pick.get("wikipedia", ""))
        if not sources:
            log("  no encyclopedia article found, next topic")
            continue
        script, feedback = None, ""
        for attempt in range(3):
            try:
                draft = brain.write_curiosity(pick, sources, feedback)
            except Exception as exc:
                log(f"  could not write it: {exc}")
                break
            n_words = sum(len(sc["narration"].split()) for sc in draft["scenes"])
            if n_words < int(cur.get("min_words", 155)):
                feedback = (f"- The narration has only {n_words} words; it must have 165-185 (about 60 seconds). "
                            "Explain the WHY in more depth with more facts from the sources; do not repeat sentences.")
                log(f"  draft {attempt + 1} too short ({n_words} words), asking for a longer one")
                continue
            check = brain.verify(draft, sources, compare_headline=False)
            if str(check.get("approved")).lower() in {"true", "yes", "1"}:
                script = draft
                break
            feedback = "\n".join(f"- {p}" for p in check.get("problems", []))
            log(f"  fact-check rejected draft {attempt + 1}:\n{feedback}")
        if not script:
            log("  skipping this topic (could not pass the fact-check)")
            continue
        sharp = brain.sharpen(script, pick.get("query", topic), topic)
        if _overlap(sharp["scenes"][0]["narration"], script["scenes"][1]["narration"]) > 0.4:
            # the new opening line would just repeat scene 2: keep the original opening, take only the title
            sharp["scenes"][0]["narration"] = script["scenes"][0]["narration"]
        if (sharp["title"], sharp["scenes"][0]["narration"]) != (script["title"], script["scenes"][0]["narration"]):
            if str(brain.verify(sharp, sources, compare_headline=False).get("approved")).lower() in {"true", "yes", "1"}:
                script = sharp
                log("  the contest winner passed the fact-check")
        script = polish.clean_script(script)
        hook_check = polish.hook_score(script["scenes"][0]["narration"])
        log(f"  title: {script['title']}\n  hook score: {hook_check['score']} ({hook_check['verdict']})")
        tags = brain.choose_hashtags(script, youtube.popular_hashtags(yt, script["search_keywords"]), [])

        run_dir = render.reset_run_dir()
        # illustrations first: stock sites rarely have the exact thing (e.g. a border line painted on a library floor)
        media_list = media.gather(script, run_dir, second=True, place=pick.get("place"), editorial=True)
        voice_name = pick_voice(cfg, history + [{}] * 3)   # shifted, so it rarely matches the 19:00 news voice
        log(f"  voice: {voice_name}")
        audio, timings, words = voice.narrate(script["scenes"], voice_name, cfg["voice_speed"])
        duration = assemble.build_mix(audio, timings, f"{run_dir}/mix.wav")
        props = assemble.build_props(script, timings, words, media_list, cfg["channel_name"], "run/mix.wav", duration)
        out = str(OUTPUT / f"explained_{dt.datetime.utcnow():%Y%m%d_%H%M}.mp4")
        render.render(props, out)

        visuals = sorted({"Pixabay" if "Pixabay" in (m or {}).get("credit", "") else
                          "Pexels" if "Pexels" in (m or {}).get("credit", "") else
                          "AI-generated images (FLUX)" if "AI" in (m or {}).get("credit", "") else ""
                          for m in media_list} - {""})
        description = (
            "🌍 World Explained: a new curiosity about our world every evening at 21:00 CET.\n\n"
            f"{script['description']}\n\n"
            + (f"💬 {script['question']}\n\n" if script.get("question") else "")
            + "Sources (Wikipedia, CC BY-SA):\n" + "\n".join(f"• {s['title']}: {s['link']}" for s in sources)
            + "\n\nNarration voice is AI-generated. Maps: Natural Earth."
            + (" Visuals: " + "; ".join(visuals) + "." if visuals else "")
            + (f"\n{assemble.music_credit()}" if assemble.music_credit() else "") + "\n\n" + " ".join(tags)
        )
        caption = instagram.caption_for(script["title"], script["description"], ["Wikipedia"], tags,
                                        script.get("question", ""), cfg.get("youtube_handle", ""),
                                        assemble.music_credit(short=True),
                                        extra_tags=tuple(cur.get("instagram_tags") or ("#geography", "#history")))
        if dry_run:
            polish.check_caption(caption, script["search_keywords"])
            log("Test mode: not uploading.")
            summary(f"### 🧪 World Explained: {script['title']}\n- Topic: {topic}\n- Voice: {voice_name}")
            return
        publish_at = publish_slot if cfg["privacy"] == "public" else None
        video_id = youtube.upload(yt, out, script["title"], description, tags, "explained", cfg["privacy"],
                                  cfg.get("ai_disclosure", True), publish_at)
        log(f"  done: https://youtube.com/shorts/{video_id}")
        history.append({"date": dt.datetime.utcnow().isoformat(timespec="minutes"), "topic": topic,
                        "title": script["title"], "video_id": video_id, "publish_at": publish_at, "slot": slot,
                        "sources": [s["link"] for s in sources], "hook": script["scenes"][0]["narration"],
                        "hook_score": hook_check["score"], "voice": voice_name, "seconds": round(duration, 1),
                        "demand": pick.get("demand"), "music": (assemble.LAST_MUSIC or {}).get("title")})
        HISTORY.write_text(json.dumps(history[-500:], indent=1, ensure_ascii=False))
        (OUTPUT / "ig.json").write_text(json.dumps({
            "title": script["title"], "slot": slot, "publish_at": publish_at, "video_id": video_id,
            "video": os.path.basename(out), "caption": caption, "question": script.get("question", ""),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        summary(f"### ✅ World Explained: {script['title']}\n- https://youtube.com/shorts/{video_id}\n- Topic: {topic}")
        return
    sys.exit("No topic could be turned into a World Explained video this time.")


if __name__ == "__main__":
    due_check() if "--check" in sys.argv else main()
