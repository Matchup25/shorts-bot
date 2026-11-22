"""Small helpers shared by every part of the bot."""
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
MODELS = ROOT / "models"
CACHE = ROOT / ".cache"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    # Optional override from the GitHub "Run workflow" button
    override = os.environ.get("PRIVACY_OVERRIDE", "").strip()
    if override in {"private", "unlisted", "public"}:
        cfg["privacy"] = override
    return cfg


def env(name: str, required: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if required and not value:
        sys.exit(f"Missing secret {name}. Add it in GitHub → Settings → Secrets and variables → Actions.")
    return value


def load_history() -> list:
    path = DATA / "history.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_history(history: list) -> None:
    DATA.mkdir(exist_ok=True)
    (DATA / "history.json").write_text(json.dumps(history[-300:], indent=2, ensure_ascii=False), encoding="utf-8")
