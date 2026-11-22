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
    def pick_stories(self, stories: list, history: list) -> list:
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

Today's stories:
{listing}

Return JSON: {{"picks": [{{"id": <number>, "why": "<one short sentence>"}}]}} with the 5 best stories, best first."""
        result = self.ask(prompt, temperature=0.4)
        ids = []
        for p in result.get("picks", []):
            try:
                ids.append(int(str(p.get("id")).strip("[] ")))
            except (TypeError, ValueError):
                continue
        by_id = {s["id"]: s for s in stories}
        return [by_id[i] for i in ids if i in by_id]

    def write_script(self, story: dict, sources: list, feedback: str = "") -> dict:
        source_block = "\n\n".join(f"SOURCE {i+1} ({s['source']}): {s['title']}\n{s['text']}" for i, s in enumerate(sources))
        fix = f"\nA fact-checker rejected your previous draft. Fix these problems:\n{feedback}\n" if feedback else ""
        prompt = f"""Write a YouTube Short (cinematic animated news explainer) about this news story.
Use ONLY facts stated in the sources below. Never invent numbers, quotes, names or dates. If sources disagree, use the
cautious version. Neutral tone, no opinions on politics. Write in English, simple words, short punchy sentences.
{fix}
RULES
- 5 to 7 scenes. Total narration 105-135 words (about 45 seconds).
- Scene 1 is the hook: one surprising sentence that creates curiosity (true to the story).
- Last scene ends with: "Follow for more stories like this."
- "headline": 2 to 5 words shown big on screen (uppercase-friendly), different from the narration.
- "visual" for each scene (what the viewer SEES behind the text):
    {{"kind": "media",
     "footage": "<2-4 word stock VIDEO search in English, concrete and filmable, e.g. 'telescope night sky', 'container ship ocean', 'city traffic timelapse'>",
     "ai_prompt": "<one vivid sentence describing a beautiful cinematic image of this moment; no real people's faces, no logos, no text>",
     "nasa": "<only for space/astronomy stories: 2-4 word NASA image search, e.g. 'Chandra galaxy', else empty>"}}
    or for 1-2 scenes with a striking number from the sources:
    {{"kind": "stat", "value": "<number only, e.g. 113>", "unit": "<short unit, e.g. days per orbit>",
     "footage": "...", "ai_prompt": "...", "nasa": "..."}}
  Make every scene look different (different places, scales, colours).
- "title": a curiosity "bait" title, max 65 characters, 0-1 emoji. It must be TRUE to the story (no fake claims,
  no "you won't believe"), for example: "This 'Dead' Star Fooled Astronomers for 15 Years".
- "category": one of {CATEGORIES}.
- "description": 2 sentences summarising the story for the YouTube description.
- "search_keywords": 2-4 short keywords to find similar videos.
- "claims": list every factual claim used in the narration and title.

SOURCES
{source_block}

Return JSON:
{{"title": "...", "category": "...", "scenes": [{{"narration": "...", "headline": "...", "visual": {{...}}}}],
 "description": "...", "search_keywords": ["..."], "claims": ["..."]}}"""
        script = self.ask(prompt, temperature=0.8)
        return _normalise_script(script)

    def verify(self, script: dict, sources: list) -> dict:
        source_block = "\n\n".join(f"SOURCE {i+1} ({s['source']}):\n{s['text']}" for i, s in enumerate(sources))
        narration = "\n".join(f"- {sc['narration']}" for sc in script["scenes"])
        prompt = f"""You are a strict fact-checker. Check the TITLE, HEADLINES and NARRATION of a news Short against the
sources. Reject if any claim is not supported by the sources, if a number/name/date is wrong, if the title is misleading,
or if anything could be defamatory or unfair to a real person. Small simplifications are fine.

TITLE: {script['title']}
HEADLINES: {[sc['headline'] for sc in script['scenes']]}
NARRATION:
{narration}

{source_block}

Return JSON: {{"approved": true/false, "problems": ["..."]}}"""
        return self.ask(prompt, temperature=0.0)

    def choose_hashtags(self, script: dict, candidates: list, trends: list) -> list:
        prompt = f"""Pick hashtags for this YouTube Short. Title: "{script['title']}". Topic: {script['description']}

Hashtags used right now by the most viewed similar Shorts (with how often they appear):
{candidates[:40]}

Google search trends right now (only use one if it is truly related to the topic):
{trends[:25]}

Choose 5 hashtags: the most popular ones that are RELEVANT to this video (misleading hashtags are against YouTube rules).
Format: "#word" with no spaces. Return JSON: {{"hashtags": ["#...", ...]}}"""
        result = self.ask(prompt, temperature=0.3)
        tags = []
        for tag in result.get("hashtags", []):
            tag = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(tag))
            if len(tag) > 2 and tag.lower() not in [t.lower() for t in tags]:
                tags.append(tag)
        return tags[:5]


# ---------------------------------------------------------------------- helpers
def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
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
        for key in ("footage", "ai_prompt", "nasa"):
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
        "claims": script.get("claims", []),
    }
