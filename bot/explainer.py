"""Second channel: Shorts that explain how the world really works (any topic, A to Z).

Topics come from topics.txt (one per line, edit it on GitHub whenever you like; the first topic not yet done is
used). When the list is empty the bot proposes topics itself and picks the one people watch most on YouTube.
Facts come from encyclopedia articles (research.py) and pass the same strict fact-check as the news Shorts.
Publishing times, channel name and voice are in config.yaml under "explainer".

  python -m bot.explainer          (DRY_RUN=true: make the video but do not upload)
"""
import datetime as dt
import json
import os
import re
import sys

from . import slots
from .util import DATA, OUTPUT, ROOT, load_config, log

HISTORY = DATA / "explainer_history.json"
TOPICS = ROOT / "topics.txt"
TOKEN_ENV = "YT2_REFRESH_TOKEN"
NEWS_CHANNEL_ID = "UCzhEYJIiDH-VR3uHWgEa-Ng"   # World in a Shot: explainers must never go there


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def load_history() -> list:
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def listed_topics() -> list:
    if not TOPICS.exists():
        return []
    out = []
    for line in TOPICS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")


def candidates(brain, ex: dict, history: list, yt) -> list:
    """Topics to try, best first: Luca's list in order, otherwise proposals ranked by YouTube demand."""
    from . import youtube
    done = {_norm(h["topic"]) for h in history}
    mine = [{"topic": t, "wikipedia": "", "query": t} for t in listed_topics() if _norm(t) not in done]
    if mine:
        log(f"  {len(mine)} topics left in topics.txt")
        return mine[:3]
    ideas = [t for t in brain.explainer_topics([h["topic"] for h in history], ex.get("categories", []))
             if _norm(t["topic"]) not in done]
    if yt:
        for t in ideas:
            d = youtube.shorts_demand(yt, t.get("query") or t["topic"], hours=24 * 30)
            t["demand"] = d["views"] if d else 0
        ideas.sort(key=lambda t: t.get("demand", 0), reverse=True)
        for t in ideas:
            log(f"    {t.get('demand', 0):>10} views/30d  {t['topic']}")
    return ideas[:3]


def due_check() -> None:
    """Cheap check for the workflow: is an explainer Short due? (writes due=true/false)"""
    cfg = load_config()
    ex = cfg.get("explainer") or {}
    test = os.environ.get("DRY_RUN", "").lower() == "true"
    connected = bool(os.environ.get(TOKEN_ENV, "").strip())
    slot_cfg = {**cfg, "publish_times": ex.get("publish_times") or []}
    due = test or (connected and (not slots.uses_slots(slot_cfg)
                                  or bool(slots.choose(slot_cfg, load_history(), slots.is_manual())[0])))
    log(f"Explainer Short due: {due}" + ("" if connected or test else " (channel not connected yet)"))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"due={'true' if due else 'false'}\n")


def main() -> None:
    from . import assemble, media, render, research, voice, youtube   # heavy: only needed when making a video
    from .brain import Brain
    cfg = load_config()
    ex = cfg.get("explainer") or {}
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    if not dry_run and not os.environ.get(TOKEN_ENV, "").strip():
        log("The explainer channel is not connected yet (YT2_REFRESH_TOKEN missing): nothing to do.")
        return
    history = load_history()
    OUTPUT.mkdir(exist_ok=True)
    slot_cfg = {**cfg, "publish_times": ex.get("publish_times") or []}
    slot, publish_slot = None, None
    if slots.uses_slots(slot_cfg):
        slot, publish_slot = slots.choose(slot_cfg, history, slots.is_manual())
        if not slot:
            log("No explainer Short is due right now.")
            return
        log(f"Making the explainer Short for slot {slot} UTC")

    brain = Brain(cfg)
    yt = youtube.service(TOKEN_ENV) if os.environ.get(TOKEN_ENV, "").strip() else None
    if yt and not dry_run:
        # safety: never publish an explainer on the news channel (or any channel not named like the explainer one)
        mine = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        title = mine[0]["snippet"]["title"] if mine else ""
        wanted = _norm(ex.get("channel_title", "RerumFabrica")).replace(" ", "")
        if not mine or mine[0]["id"] == NEWS_CHANNEL_ID or _norm(title).replace(" ", "") != wanted:
            sys.exit(f"YT2_REFRESH_TOKEN belongs to the channel '{title}', not to RerumFabrica: nothing published.")
    forced = os.environ.get("FORCE_TOPIC", "").strip()
    picks = [{"topic": forced, "wikipedia": "", "query": forced}] if forced else candidates(brain, ex, history, yt)

    for pick in picks:
        topic = pick["topic"]
        log(f"Topic: {topic}")
        sources = research.sources_for(topic, pick.get("wikipedia", ""))
        if not sources:
            log("  no reference article found, next topic")
            continue
        script, feedback = None, ""
        for attempt in range(3):
            draft = brain.write_explainer(topic, sources, feedback)
            check = brain.verify(draft, sources, compare_headline=False)
            if check.get("approved"):
                script = draft
                break
            feedback = "\n".join(f"- {p}" for p in check.get("problems", []))
            log(f"  fact-check rejected draft {attempt + 1}:\n{feedback}")
        if not script:
            log("  skipping this topic (could not pass the fact-check)")
            continue
        sharp = brain.sharpen(script, pick.get("query", topic), topic)
        if (sharp["title"], sharp["scenes"][0]["narration"]) != (script["title"], script["scenes"][0]["narration"]):
            if brain.verify(sharp, sources, compare_headline=False).get("approved"):
                script = sharp
        log(f"  title: {script['title']}")
        tags = brain.choose_hashtags(script, youtube.popular_hashtags(yt, script["search_keywords"]) if yt else [], [])

        run_dir = render.reset_run_dir()
        media_list = media.gather(script, run_dir, second=True)
        audio, timings, words = voice.narrate(script["scenes"], ex.get("voice", cfg["voice"]),
                                              ex.get("voice_speed", cfg["voice_speed"]))
        duration = assemble.build_mix(audio, timings, f"{run_dir}/mix.wav")
        props = assemble.build_props(script, timings, words, media_list, ex.get("channel_name", "RERUMFABRICA"),
                                     "run/mix.wav", duration)
        out = str(OUTPUT / f"explainer_{dt.datetime.utcnow():%Y%m%d_%H%M}.mp4")
        render.render(props, out)

        description = (
            f"{script['description']}\n\n"
            + (f"💬 {script['question']}\n\n" if script.get("question") else "")
            + "This video explains how things work and what professionals do. It is not a how-to guide: "
              "rules differ between countries, and risky work belongs to qualified professionals.\n\n"
            + "Sources (CC BY-SA):\n" + "\n".join(f"• Wikipedia – {s['title']}: {s['link']}" for s in sources)
            + "\n\nNarration voice is AI-generated. Visuals: Pixabay / Pexels stock footage.\n\n" + " ".join(tags)
        )
        if dry_run:
            log("Test mode: not uploading.")
            summary(f"### 🧪 {script['title']}\n- Topic: {topic}\n- Sources: {', '.join(s['title'] for s in sources)}")
            return
        publish_at = publish_slot if cfg["privacy"] == "public" else None
        video_id = youtube.upload(yt, out, script["title"], description, tags, "education", cfg["privacy"],
                                  cfg.get("ai_disclosure", True), publish_at)
        log(f"  done: https://youtube.com/shorts/{video_id}")
        history.append({"date": dt.datetime.utcnow().isoformat(timespec="minutes"), "topic": topic,
                        "title": script["title"], "video_id": video_id, "publish_at": publish_at, "slot": slot,
                        "sources": [s["link"] for s in sources], "hook": script["scenes"][0]["narration"],
                        "seconds": round(duration, 1), "demand": pick.get("demand")})
        HISTORY.write_text(json.dumps(history[-500:], indent=1, ensure_ascii=False))
        (OUTPUT / "golive.json").write_text(json.dumps({
            "video_id": video_id, "publish_at": publish_at, "question": script.get("question", ""),
            "token_env": TOKEN_ENV}, ensure_ascii=False))
        summary(f"### ✅ {script['title']}\n- https://youtube.com/shorts/{video_id}\n- Topic: {topic}")
        return
    sys.exit("No topic could be turned into a Short this time.")


if __name__ == "__main__":
    due_check() if "--check" in sys.argv else main()
