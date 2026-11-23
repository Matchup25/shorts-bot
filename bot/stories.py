"""Instagram Stories, several times a day: "LAST MINUTE" news flashes and "DID YOU KNOW?" facts.

Each wake-up of the bot starts this step; it posts a story only when one of the story times
(config `story_times`, Zurich time) has passed less than 2.5 hours ago and was not posted yet.
Content comes from the same news feeds as the Shorts and is fact-checked against the article:
the card may never say more than the outlet's own headline and article.
The card is drawn as a 1080x1920 picture (HTML + Chrome), turned into a 7-second video and
published with the Instagram API (needs a business account).

  python -m bot.stories          → post a story if one is due
  python -m bot.stories --force  → post one now (test)
  python -m bot.stories --dry    → only draw the card (no publishing), saved in output/
"""
import argparse
import datetime as dt
import html
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from . import instagram, media, news
from .brain import Brain
from .util import DATA, OUTPUT, ROOT, load_config, load_history, log

HISTORY = DATA / "stories_history.json"
WINDOW = dt.timedelta(minutes=150)
DEFAULT_TIMES = ["06:47", "09:47", "12:47", "15:47", "18:47", "21:47"]
KINDS = ["last_minute", "fact"]


def _load() -> list:
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def due_slot(cfg: dict, hist: list, now: dt.datetime) -> tuple[str, str] | None:
    """(slot key, kind) of the story that should go out now, or None."""
    tz = ZoneInfo(cfg.get("timezone", "Europe/Zurich"))
    local = now.astimezone(tz)
    done = {h.get("slot") for h in hist}
    times = cfg.get("story_times") or DEFAULT_TIMES
    for day in (0, -1):
        date = (local + dt.timedelta(days=day)).date()
        for i, hhmm in enumerate(times):
            h, m = (int(x) for x in hhmm.split(":"))
            t = dt.datetime(date.year, date.month, date.day, h, m, tzinfo=tz)
            key = t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            if t <= now < t + WINDOW and key not in done:
                return key, KINDS[i % len(KINDS)]
    return None


def choose(brain: Brain, cfg: dict, kind: str, used: set) -> tuple[dict, dict] | None:
    """Pick a story and write the card. Returns (story, card)."""
    stories = [s for s in news.fetch_stories(cfg) if s["link"] not in used]
    now = time.time()
    if kind == "last_minute":
        fresh = [s for s in stories if now - s["published"] < 4 * 3600] or \
                [s for s in stories if now - s["published"] < 8 * 3600]
    else:
        fresh = stories
    if not fresh:
        return None
    listing = "\n".join(f"[{i}] ({s['source']}) {s['title']} — {s['summary'][:200]}" for i, s in enumerate(fresh[:60]))
    avoid = "; ".join(cfg.get("avoid_topics", []))
    if kind == "last_minute":
        task = """Pick the most important or most interesting story that has JUST broken and write a "LAST MINUTE" news
flash card: "headline" = the news in max 9 words (no clickbait), "text" = one or two plain sentences with the key
facts (max 28 words)."""
    else:
        task = """Pick the story that contains the most surprising, delightful fact and write a "DID YOU KNOW?" card:
"headline" = that fact as one striking line (max 10 words), "text" = one or two sentences of context
(max 28 words). The fact must be stated in the article, not general knowledge."""
    prompt = f"""You write Instagram Stories for "World in a Shot", an English news channel for an international audience.
{task}
Neutral tone, no opinions, nothing graphic. NEVER pick: {avoid}. Avoid tragedies with victims.
"photo": 2-4 word stock photo search for a calm background picture (no real people's faces, no logos), e.g.
"parliament building night", "telescope stars", "container ship sea".

Stories:
{listing}

Return JSON: {{"id": <number>, "headline": "...", "text": "...", "photo": "..."}}"""
    card = brain.ask(prompt, temperature=0.6)
    try:
        story = fresh[int(str(card.get("id")).strip("[] "))]
    except (TypeError, ValueError, IndexError):
        return None
    story["text"] = news.article_text(story["link"], fallback=f"{story['title']}. {story['summary']}")
    return story, card


def check(brain: Brain, story: dict, card: dict) -> bool:
    prompt = f"""You are a strict fact-checker for a news channel. Viewers see only this Instagram Story card.

THE NEWS OUTLET'S OWN HEADLINE: {story['title']}
CARD HEADLINE: {card.get('headline')}
CARD TEXT: {card.get('text')}

ARTICLE ({story['source']}):
{story['text'][:6000]}

List every impression a viewer gets from the card, and for each copy the exact article sentence that proves it
("" if none). Supported only with the same certainty and the same subject (a claim, a plan or partial progress
does not support "done"). Also say whether the card claims more than the outlet's own headline.
Return JSON: {{"impressions": [{{"claim": "...", "evidence": "...", "supported": true}}],
 "stronger_than_outlet": false, "approved": true, "problems": ["..."]}}"""
    res = brain.ask(prompt, temperature=0.0)
    imps = res.get("impressions") or []
    weak = [i for i in imps if not i.get("supported") or not str(i.get("evidence", "")).strip()]
    ok = str(res.get("approved")).lower() in {"true", "yes", "1"} and imps and not weak \
        and res.get("stronger_than_outlet") not in (True, "true", "True")
    if not ok:
        log("  card rejected by the fact-check: " + "; ".join(
            [str(i.get("claim")) for i in weak] + [str(p) for p in res.get("problems") or []]))
    return bool(ok)


def draw(card: dict, story: dict, kind: str, workdir: str, cfg: dict) -> str:
    """Card picture (1080x1920 PNG) drawn with Chrome from an HTML template."""
    os.makedirs(workdir, exist_ok=True)
    bg = os.path.join(workdir, "bg.jpg")
    photo = media.pixabay_photo(card.get("photo") or "", bg, set())
    fonts = ROOT / "video" / "public" / "fonts"
    logo = ROOT / "video" / "public" / "brand" / "logo.png"
    tz = ZoneInfo(cfg.get("timezone", "Europe/Zurich"))
    stamp = dt.datetime.now(tz).strftime("%H:%M %Z")
    kicker, color = ("LAST MINUTE", "#FF3B3B") if kind == "last_minute" else ("DID YOU KNOW?", "#FFD23F")
    bg_css = (f"url('file://{bg}') center/cover no-repeat" if photo else
              "radial-gradient(ellipse 90% 60% at 50% 30%,#2A2F48 0%,#141725 55%,#07080D 100%)")
    headline_len = len(str(card.get("headline", "")))
    size = 104 if headline_len <= 34 else 90 if headline_len <= 50 else 78
    page = f"""<html><head><style>
@font-face{{font-family:Anton;src:url('file://{fonts}/Anton-Regular.ttf')}}
@font-face{{font-family:Mont;src:url('file://{fonts}/Montserrat.ttf');font-weight:100 900}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1920px;overflow:hidden;background:{bg_css};font-family:Mont,sans-serif;color:#fff;position:relative}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.55) 0%,rgba(7,8,13,.25) 30%,rgba(7,8,13,.82) 58%,rgba(7,8,13,.96) 100%)}}
.brand{{position:absolute;top:150px;left:70px;display:flex;align-items:center;gap:22px;font-weight:800;font-size:34px;letter-spacing:3px}}
.brand img{{width:84px;height:84px;border-radius:50%}}
.box{{position:absolute;left:70px;right:70px;bottom:250px;display:flex;flex-direction:column;align-items:flex-start;gap:30px}}
.kicker{{background:{color};color:{'#fff' if kind == 'last_minute' else '#07080D'};
 font-weight:900;font-size:38px;letter-spacing:6px;padding:14px 28px;border-radius:10px}}
.kicker span{{display:inline-block;width:16px;height:16px;border-radius:50%;background:currentColor;margin-right:14px;vertical-align:4px}}
h1{{font-family:Anton;font-weight:400;font-size:{size}px;line-height:1.04;text-transform:uppercase}}
p{{font-size:40px;line-height:1.38;font-weight:500;color:#E6E8F2}}
.src{{font-size:28px;font-weight:700;color:#FFD23F;letter-spacing:1px}}
</style></head><body><div class="shade"></div>
<div class="brand"><img src="file://{logo}">WORLD IN A SHOT</div>
<div class="box"><div class="kicker"><span></span>{kicker}</div>
<h1>{html.escape(str(card.get('headline', '')))}</h1>
<p>{html.escape(str(card.get('text', '')))}</p>
<div class="src">Source: {html.escape(story['source'])} · {stamp}</div></div>
</body></html>"""
    page_path = os.path.join(workdir, "card.html")
    with open(page_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    png = os.path.join(workdir, "card.png")
    chrome = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                    "--allow-file-access-from-files", "--force-device-scale-factor=1", "--window-size=1080,1920",
                    "--virtual-time-budget=4000", f"--screenshot={png}", f"file://{page_path}"],
                   check=True, capture_output=True, timeout=120)
    return png


def to_video(png: str, out: str, seconds: int = 7) -> str:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", png,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", "scale=1080:1920,format=yuv420p", "-r", "30", "-t", str(seconds),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest",
                    "-movflags", "+faststart", out], check=True, timeout=180)
    return out


def publish(video: str) -> str:
    token, acc = instagram.get_token()
    if acc["mode"] != "facebook":
        raise RuntimeError("Stories need the Unified-login (business) setup")
    container = instagram._container_upload(acc, token, video, "", media_type="STORIES")
    instagram._wait_ready(acc["api"], token, container)
    r = instagram._call("POST", f"{acc['api']}/{acc['ig_id']}/media_publish", token, creation_id=container)
    if not r.ok:
        raise RuntimeError(f"Instagram did not publish the story: {r.text[:400]}")
    return r.json()["id"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--kind", choices=KINDS, default=None)
    args = ap.parse_args()
    cfg = load_config()
    hist = _load()
    now = dt.datetime.now(dt.timezone.utc)
    slot = due_slot(cfg, hist, now)
    if args.force or args.dry:
        slot = (now.strftime("%Y-%m-%dT%H:%MZ") + "-manual", args.kind or "last_minute")
    if not slot:
        log("No story due right now.")
        return
    key, kind = slot
    log(f"Story for {key} ({kind})")
    brain = Brain(cfg)
    used = {h.get("link") for h in hist} | {link for h in load_history() for link in h.get("links", [])}
    for attempt in range(3):
        picked = choose(brain, cfg, kind, used)
        if not picked:
            log("  nothing suitable found")
            break
        story, card = picked
        log(f"  {story['source']}: {story['title']}\n  card: {card.get('headline')} / {card.get('text')}")
        if check(brain, story, card):
            break
        used.add(story["link"])
        picked = None
    if not picked:
        if kind == "fact" and not args.kind:  # no good fact: a news flash instead
            kind = "last_minute"
            picked = choose(brain, cfg, kind, used)
            if picked and not check(brain, *picked):
                picked = None
        if not picked:
            sys.exit("No story passed the fact-check this time.")
    story, card = picked
    OUTPUT.mkdir(exist_ok=True)
    work = str(OUTPUT / "story")
    png = draw(card, story, kind, work, cfg)
    video = to_video(png, str(OUTPUT / "story.mp4"))
    if args.dry:
        log(f"  test only: card saved in {png}")
        return
    media_id = publish(video)
    log(f"  story published ({media_id})")
    hist.append({"slot": key, "kind": kind, "date": now.isoformat(timespec="minutes"), "title": story["title"],
                 "link": story["link"], "headline": card.get("headline"), "media_id": media_id})
    HISTORY.write_text(json.dumps(hist[-400:], indent=1, ensure_ascii=False))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(f"### 📱 Story ({kind}): {card.get('headline')}\n- {story['source']}: {story['link']}\n")


if __name__ == "__main__":
    main()
