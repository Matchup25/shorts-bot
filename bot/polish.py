"""Final polish of the texts before they go out (titles, narration, descriptions, captions).

- clean():          removes the typical "written by an AI" marks (invisible characters, em dashes, words like
                    "delve" or "game-changing"); meaning and facts stay the same.
- hook_score():     0-100 score of an opening line (length, concrete detail, tension, payoff up front).
- check_caption():  what Instagram shows before "... more", hashtag count, links.

The checks come from instagram-agent-skill (MIT), see bot/vendor/README.md.
"""
import json
import re
from pathlib import Path

from .util import log
from .vendor import caption as _caption
from .vendor import hookscore as _hookscore
from .vendor import humanize as _humanize

_LEX = json.loads((Path(__file__).parent / "vendor" / "slop.json").read_text(encoding="utf-8"))
_ZWJ_EMOJI = re.compile("([\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F])\u200d(?=[\U0001F300-\U0001FAFF\u2600-\u27BF])")


def clean(text: str) -> str:
    """Same meaning, fewer AI fingerprints. Emoji made of several parts stay intact."""
    if not text or not text.strip():
        return text
    protected = _ZWJ_EMOJI.sub("\\1\x01", text)
    out, _report = _humanize.humanize(protected, _LEX)
    out = out.strip().replace("\x01", "\u200d")
    return out or text


def clean_script(script: dict) -> dict:
    """Polish every text of a script; logs what changed."""
    changed = []

    def fix(value: str, where: str) -> str:
        new = clean(value)
        if new != value:
            changed.append(f"{where}: {value!r} -> {new!r}")
        return new

    script = dict(script)
    script["title"] = fix(script.get("title", ""), "title")
    for key in ("description", "question"):
        if script.get(key):
            script[key] = fix(script[key], key)
    scenes = []
    for i, sc in enumerate(script.get("scenes", []), start=1):
        sc = dict(sc)
        sc["narration"] = fix(sc.get("narration", ""), f"scene {i}")
        if sc.get("headline"):
            sc["headline"] = fix(sc["headline"], f"headline {i}")
        scenes.append(sc)
    script["scenes"] = scenes
    if changed:
        log("  polish:\n    " + "\n    ".join(changed[:12]))
    return script


def hook_score(text: str) -> dict:
    """Heuristic quality of an opening line (not a view prediction)."""
    results, overall, verdict, flags = _hookscore.run(text or "")
    weakest = min(_hookscore.CHECKS, key=lambda c: results[c][0])
    return {"score": round(overall, 1), "verdict": verdict, "weakest": weakest, "flags": flags}


def check_caption(text: str, keywords: list | None = None) -> dict:
    """Instagram caption check; returns the linter's result and logs anything not passing."""
    res = _caption.analyse(text, keywords=keywords or [])
    problems = [f"{c['status']} {c['check']}: {c['detail']}" for c in res["checks"]
                if c["status"] != "PASS" and c["check"] != "ONE ASK"]
    log(f"  caption check: {res['verdict']}" + ("".join(f"\n    {p}" for p in problems) if problems else ""))
    return res
