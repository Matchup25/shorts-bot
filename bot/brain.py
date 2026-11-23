"""Agents 2-4 – editor, writer and fact-checker, powered by the free Gemini API."""
import json
import re
import time

from .util import env, log

CATEGORIES = ["science", "space", "tech", "world", "business", "health", "nature", "weird", "culture"]


class Brain:
    def __init__(self, cfg: dict):
        from google import genai
        self.genai = genai
        self.client = genai.Client(api_key=env("GEMINI_API_KEY"))
        self.models = list(cfg.get("gemini_models") or ["gemini-flash-latest"])
        self.cfg = cfg
        self._working_model = None

    # ------------------------------------------------------------------ core
    def _fallback_models(self) -> list:
        found = []
        try:
            for m in self.client.models.list():
                name = m.name.replace("models/", "")
                actions = getattr(m, "supported_actions", None) or []
                if "flash" in name and "generateContent" in actions and "image" not in name and "tts" not in name:
                    found.append(name)
        except Exception as exc:
            log(f"  could not list models: {exc}")
        def rank(name):
            nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", name)[:1]] or [0.0]
            return (-nums[0], "lite" in name, "preview" in name)
        return sorted(found, key=rank)

    def ask(self, prompt: str, temperature: float = 0.7) -> dict:
        """Send a prompt, get JSON back. Retries and falls back to other models."""
        from google.genai import types
        candidates = ([self._working_model] if self._working_model else []) + self.models
        tried, last_error = set(), None
        for round_ in range(2):
            for model in candidates:
                if not model or model in tried:
                    continue
                for attempt in range(4):
                    try:
                        resp = self.client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=temperature,
                                response_mime_type="application/json",
                            ),
                        )
                        self._working_model = model
                        time.sleep(float(self.cfg.get("gemini_pause_seconds", 2)))  # stay under per-minute limits
                        return _parse_json(resp.text)
                    except Exception as exc:
                        last_error = exc
                        msg = str(exc)
                        if "404" in msg or "NOT_FOUND" in msg or "not found" in msg.lower():
                            log(f"  model {model} not available, trying next")
                            break
                        wait = 20 * (attempt + 1)
                        log(f"  Gemini busy/limited ({msg[:90]}), waiting {wait}s")
                        time.sleep(wait)
                tried.add(model)
            if round_ == 0:
                candidates = self._fallback_models()
                log(f"  fallback models: {candidates[:5]}")
        raise RuntimeError(f"Gemini did not answer: {last_error}")

    # ---------------------------------------------------------------- agents
    def pick_stories(self, stories: list, history: list, trends: list | None = None) -> list:
        listing = "\n".join(
            f"[{s['id']}] ({s['source']}, reported by {s.get('outlets', 1)} outlets) {s['title']} — {s['summary'][:220]}"
            for s in stories[:150]
        )
        done = "\n".join(f"- {h['title']}" for h in history[-40:]) or "- (none yet)"
        avoid = "; ".join(self.cfg.get("avoid_topics", []))
        prompt = f"""You are the editor of a YouTube Shorts channel that turns real news into 45-second animated explainers
for an international English-speaking audience. Your goal: stories that make people stop scrolling and say "wait, what?".

GOOD: surprising science, space, technology, nature and animals, records, discoveries, strange-but-true news,
big business/tech milestones, inventions, culture phenomena. Prefer stories reported by 2+ outlets.
NEVER PICK: {avoid}. Also avoid tragedies, anything graphic, and anything that would be unfair to a private person.
Do not pick a story we already covered:
{done}

What people are searching for on Google right now (prefer stories that match these, if they fit the rules):
{", ".join((trends or [])[:30]) or "(not available)"}

Today's stories:
{listing}

Return JSON: {{"picks": [{{"id": <number>, "why": "<one short sentence>",
  "query": "<2-4 words someone would type on YouTube to find videos about this story, e.g. 'mercury probe bepicolombo'>"}}]}}
with the 6 best stories, best first."""
        result = self.ask(prompt, temperature=0.4)
        by_id = {s["id"]: s for s in stories}
        picks = []
        for p in result.get("picks", []):
            try:
                story = by_id.get(int(str(p.get("id")).strip("[] ")))
            except (TypeError, ValueError):
                continue
            if story and story not in picks:
                story["yt_query"] = str(p.get("query") or "").strip() or story["title"]
                story["why"] = str(p.get("why") or "")
                picks.append(story)
        return picks

    def sharpen(self, script: dict, query: str = "") -> dict:
        """Title and hook contest: several candidates, scored on fixed criteria; the best one wins."""
        first = script["scenes"][0]["narration"]
        last = script["scenes"][-1]["narration"]
        claims = "\n".join(f"- {c}" for c in script.get("claims", [])) or "- (see narration)"
        narration = "\n".join(f"- {sc['narration']}" for sc in script["scenes"])
        prompt = f"""You optimise YouTube Shorts for news. Viewers decide in under 2 seconds whether to keep watching,
from the TITLE in the feed and the FIRST SENTENCE they hear.

Current title: {script['title']}
Current first sentence (hook): {first}
Last sentence (the Short loops back to the hook, so the hook must still follow naturally from it): {last}
What people search on YouTube for this topic: {query or "(unknown)"}
Full narration:
{narration}
Facts you may use (nothing else):
{claims}

1. Write 5 NEW title candidates (max 50 characters, 0-1 emoji, include the search keyword when natural).
2. Write 3 NEW hook candidates (max 14 words, the most surprising fact or number first).
TRUTH COMES FIRST: keep exactly who did what and how certain it is. Never turn "helped" into "solved", "may" into
"will", "claims" into "proved", an attempt or a partial result into a success, or a related problem into a famous one
(e.g. progress on a question linked to the Riemann hypothesis is NOT "solved the Riemann hypothesis").
3. Score every candidate, including the current title and current hook, from 0 to 10 on:
   curiosity (makes you need to know more), clarity (understood instantly, no jargon),
   keyword (uses words people search), truth (fully supported by the facts above; anything unsupported or
   exaggerated = 0 and the candidate is out).
Return JSON:
{{"titles": [{{"text": "...", "curiosity": 0, "clarity": 0, "keyword": 0, "truth": 0}}],
 "hooks": [{{"text": "...", "curiosity": 0, "clarity": 0, "keyword": 0, "truth": 0}}]}}"""
        try:
            result = self.ask(prompt, temperature=0.9)
        except Exception as exc:
            log(f"  title contest skipped: {exc}")
            return script

        def best(items, current, max_len, max_words):
            scored = []
            for it in items or []:
                text = str(it.get("text", "")).strip().strip('"')
                try:
                    truth = float(it.get("truth", 0))
                    total = float(it.get("curiosity", 0)) * 1.5 + float(it.get("clarity", 0)) + float(it.get("keyword", 0)) * 0.5
                except (TypeError, ValueError):
                    continue
                if not text or truth < 9 or len(text) > max_len or len(text.split()) > max_words:
                    continue
                scored.append((total, text))
            scored.sort(reverse=True)
            return (scored[0][1] if scored else current), scored[:6]

        title, t_scores = best(result.get("titles"), script["title"], 60, 12)
        hook, h_scores = best(result.get("hooks"), first, 120, 16)
        script = dict(script)
        script["scenes"] = [dict(sc) for sc in script["scenes"]]
        script["title"] = title
        script["scenes"][0]["narration"] = hook
        script["contest"] = {"titles": t_scores, "hooks": h_scores}
        log(f"  title: {title}\n  hook: {hook}")
        return script

    def write_script(self, story: dict, sources: list, feedback: str = "") -> dict:
        source_block = "\n\n".join(f"SOURCE {i+1} ({s['source']}): {s['title']}\n{s['text']}" for i, s in enumerate(sources))
        fix = f"\nA fact-checker rejected your previous draft. Fix these problems:\n{feedback}\n" if feedback else ""
        prompt = f"""Write a YouTube Short (cinematic animated news explainer) about this news story.
Use ONLY facts stated in the sources below. Never invent numbers, quotes, names or dates. If sources disagree, use the
cautious version. Neutral tone, no opinions on politics. Write in English, simple words, short punchy sentences.
{fix}
RULES
- 4 or 5 scenes. Total narration 75-95 words (about 30 seconds): short Shorts are watched to the end.
- Scene 1 is the hook and must make people stop scrolling in under 2 seconds: start with the most surprising
  fact or number of the story itself (the payoff first, not a setup), max 14 words, true to the story.
- Every following sentence adds a new fact. No filler, no greeting, no "in today's video".
- The last sentence must lead naturally back to the first one, so the Short loops seamlessly when it restarts.
  Do NOT end with "follow", "subscribe" or any call to action.
- "headline": 2 to 5 words shown big on screen (uppercase-friendly), different from the narration.
- "visual" for each scene (what the viewer SEES behind the text):
    {{"kind": "media",
     "footage": "<2-4 word stock VIDEO search in English, concrete and filmable, e.g. 'telescope night sky', 'container ship ocean', 'city traffic timelapse'>",
     "footage2": "<a DIFFERENT 2-4 word stock video search for a second shot of the same moment (another angle or a close-up)>",
     "ai_prompt": "<one vivid sentence describing a beautiful cinematic image of this moment; no real people's faces, no logos, no text>",
     "nasa": "<only for space/astronomy stories: 2-4 word NASA image search, e.g. 'Chandra galaxy', else empty>"}}
    or for 1-2 scenes with a striking number from the sources:
    {{"kind": "stat", "value": "<number only, e.g. 113>", "unit": "<short unit, e.g. days per orbit>",
     "footage": "...", "ai_prompt": "...", "nasa": "..."}}
  Make every scene look different (different places, scales, colours).
  Footage must never show the WRONG place: if the story is about a specific country or city, either name it in the
  search ("seoul city night") or choose neutral close-ups (hands on phone, exam paper, microphone, documents).
  Use simple, literal, filmable words that a stock video site would tag, not abstract ideas.
- "title": a curiosity "bait" title, max 50 characters (longer titles get cut in the Shorts feed), with the main
  keyword people would search, 0-1 emoji. It must be TRUE to the story (no fake claims, no "you won't believe"),
  for example: "This 'Dead' Star Fooled Astronomers for 15 Years".
- "category": one of {CATEGORIES}.
- "description": 2 sentences summarising the story for the YouTube description.
- "search_keywords": 2-4 short keywords to find similar videos.
- "question": one short open question for the comments that invites viewers to share their view or experience
  about this story (max 15 words). Neutral: never take a side on politics, never mock anyone, no yes/no about
  guilt or tragedy. Example: "Would you trust an AI to check your exam answers?"
- "claims": list every factual claim used in the narration and title.

SOURCES
{source_block}

Return JSON:
{{"title": "...", "category": "...", "scenes": [{{"narration": "...", "headline": "...", "visual": {{...}}}}],
 "description": "...", "search_keywords": ["..."], "question": "...", "claims": ["..."]}}"""
        script = self.ask(prompt, temperature=0.8)
        return _normalise_script(script)

    def verify(self, script: dict, sources: list) -> dict:
        source_block = "\n\n".join(f"SOURCE {i+1} ({s['source']}):\n{s['text']}" for i, s in enumerate(sources))
        narration = "\n".join(f"- {sc['narration']}" for sc in script["scenes"])
        prompt = f"""You are a strict fact-checker for a news channel. Check the TITLE, the FIRST SENTENCE, the HEADLINES and
the NARRATION of a news Short against the sources.

Reject if:
- any claim is not supported by the sources, or a number, name or date is wrong;
- the title or the first sentence OVERSTATES the news: an attempt, a claim, a partial or related result presented as
  done or as the famous big problem ("helped" -> "solved", "may" -> "will", "claims" -> "proved", "related to X" -> "X",
  "progress on" -> "cracked"), or the action is credited to the wrong person or thing;
- the title is misleading, or anything could be defamatory or unfair to a real person.
Small simplifications of wording are fine; changes in certainty or in who did what are not.

TITLE: {script['title']}
COMMENT QUESTION (must be neutral and must not assume facts that are not in the sources): {script.get('question', '')}
FIRST SENTENCE: {script['scenes'][0]['narration']}
HEADLINES: {[sc['headline'] for sc in script['scenes']]}
NARRATION:
{narration}

{source_block}

First copy the exact source sentence that supports the TITLE and the one that supports the FIRST SENTENCE
(empty if there is none), then decide.
Return JSON: {{"title_evidence": "...", "hook_evidence": "...", "approved": true/false, "problems": ["..."]}}"""
        result = self.ask(prompt, temperature=0.0)
        if not str(result.get("title_evidence", "")).strip() or not str(result.get("hook_evidence", "")).strip():
            result["approved"] = False
            result.setdefault("problems", []).append("Title or first sentence has no supporting sentence in the sources.")
        return result

    # ------------------------------------------------------------ weekly show
    def pick_weekly(self, stories: list, count: int, date_range: str) -> list:
        listing = "\n".join(
            f"[{s['id']}] ({s['source']}, {s.get('outlets', 1)} outlets) {s['title']} — {s['summary'][:160]}"
            for s in stories[:320]
        )
        prompt = f"""You are the editor-in-chief of "World in a Shot Weekly", a neutral international news roundup on
YouTube for the week {date_range}. Pick the {count} MOST IMPORTANT stories of the week for a global audience:
politics, conflicts, economy, science, technology, climate, health, culture. Balance regions and topics, never pick two
stories about the same event, prefer stories reported by several outlets. Neutral and factual: no opinions.

Stories of the week:
{listing}

For each pick give where it happened. Return JSON:
{{"picks": [{{"id": <number>, "country": "<English country name, or Global>",
  "place": "<short place label, e.g. Seoul, South Korea>", "lat": <latitude>, "lon": <longitude>}}]}}
Most important story first."""
        result = self.ask(prompt, temperature=0.3)
        by_id = {s["id"]: s for s in stories}
        picks = []
        for p in result.get("picks", []):
            try:
                sid = int(str(p.get("id")).strip("[] "))
                place = {"label": str(p.get("place") or p.get("country") or "World"),
                         "country": str(p.get("country") or "Global"),
                         "lat": float(p.get("lat") or 0), "lon": float(p.get("lon") or 0)}
            except (TypeError, ValueError):
                continue
            if sid in by_id:
                picks.append({**by_id[sid], "place": place})
        return picks

    def write_segment(self, story: dict, sources: list, feedback: str = "") -> dict:
        source_block = "\n\n".join(f"SOURCE {i+1} ({s['source']}): {s['title']}\n{s['text']}" for i, s in enumerate(sources))
        fix = f"\nA fact-checker rejected your previous draft. Fix these problems:\n{feedback}\n" if feedback else ""
        prompt = f"""Write one segment of a neutral weekly world-news show (spoken by a news anchor, English).
Use ONLY facts stated in the sources. Never invent numbers, quotes, names or dates. Neutral, calm, factual tone:
no opinions, no loaded words, attribute claims ("officials said", "according to"). Never describe violence graphically.
{fix}
RULES
- 6 scenes, 165-195 words in total (about one minute). No greeting, no call to action.
- Scene 1 opens the story with where and what happened, in one or two sentences. Its visual is {{"kind": "map"}}.
- Scenes 2-6 explain what happened, the background, the reactions, why it matters and what comes next.
- "headline": 3 to 6 words, neutral (shown on screen).
- "category": one of {CATEGORIES}.
- visuals for scenes 2-6:
    {{"kind": "media", "footage": "<2-4 literal words for a stock VIDEO search. Prefer neutral close-ups that fit any
      country: hands typing, documents, newspaper, microphone, flag, computer screen, satellite, ambulance, ship at sea.
      Never ask for a skyline, street or city view unless you write the exact city name in the search>",
      "ai_prompt": "<one symbolic illustration idea, no real people, no fake scene of the real event>"}}
    or one striking number from the sources: {{"kind": "stat", "value": "<number only>", "unit": "<short unit>",
      "footage": "...", "ai_prompt": "..."}}
- "claims": every factual claim used.

SOURCES
{source_block}

Return JSON: {{"headline": "...", "category": "...", "scenes": [{{"narration": "...", "visual": {{...}}}}],
 "claims": ["..."]}}"""
        seg = self.ask(prompt, temperature=0.6)
        if isinstance(seg, list):  # sometimes the answer is wrapped in a list
            seg = seg[0] if seg and isinstance(seg[0], dict) else {}
        scenes = []
        for i, sc in enumerate((seg.get("scenes") or [])[:7]):
            narration = str(sc.get("narration", "")).strip()
            if not narration:
                continue
            vis = dict(sc.get("visual") or {})
            if i == 0:
                vis = {"kind": "map"}
            elif vis.get("kind") != "stat" or not str(vis.get("value", "")).strip():
                vis["kind"] = "media"
            for key in ("footage", "ai_prompt"):
                vis[key] = str(vis.get(key) or "").strip()
            scenes.append({"narration": narration, "headline": "", "visual": vis})
        if len(scenes) < 3:
            raise ValueError("segment has too few scenes")
        category = str(seg.get("category", "world")).lower()
        return {"title": str(seg.get("headline", "")).strip()[:60], "headline": str(seg.get("headline", "")).strip()[:60],
                "category": category if category in CATEGORIES else "world", "scenes": scenes,
                "claims": seg.get("claims", [])}

    def choose_hashtags(self, script: dict, candidates: list, trends: list) -> list:
        prompt = f"""Pick hashtags for this YouTube Short. Title: "{script['title']}". Topic: {script['description']}

Hashtags used right now by the most viewed similar Shorts (with how often they appear):
{candidates[:40]}

Google search trends right now (only use one if it is truly related to the topic):
{trends[:25]}

Choose 3 hashtags: the most popular ones that are RELEVANT to this video (misleading hashtags are against YouTube rules).
YouTube shows the first three above the title, more do not help.
Format: "#word" with no spaces. Return JSON: {{"hashtags": ["#...", ...]}}"""
        result = self.ask(prompt, temperature=0.3)
        tags = []
        for tag in result.get("hashtags", []):
            tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(tag))
            if len(tag) > 2 and tag.lower() not in [t.lower() for t in tags]:
                tags.append(tag)
        return tags[:3]


# ---------------------------------------------------------------------- helpers
def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _normalise_script(script: dict) -> dict:
    scenes = []
    for sc in script.get("scenes", [])[:8]:
        narration = str(sc.get("narration", "")).strip()
        if not narration:
            continue
        visual = dict(sc.get("visual") or {})
        if visual.get("kind") != "stat" or not str(visual.get("value", "")).strip():
            visual["kind"] = "media"
        for key in ("footage", "footage2", "ai_prompt", "nasa"):
            visual[key] = str(visual.get(key) or "").strip()
        scenes.append({"narration": narration, "headline": str(sc.get("headline", "")).strip()[:40], "visual": visual})
    if len(scenes) < 3:
        raise ValueError("script has too few scenes")
    category = str(script.get("category", "world")).lower()
    return {
        "title": str(script.get("title", "")).strip()[:95] or scenes[0]["headline"],
        "category": category if category in CATEGORIES else "world",
        "scenes": scenes,
        "description": str(script.get("description", "")).strip(),
        "search_keywords": [str(k) for k in script.get("search_keywords", [])][:4],
        "question": str(script.get("question", "")).strip()[:140],
        "claims": script.get("claims", []),
    }
