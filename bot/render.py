"""Agent 5c – the animator: renders the Short with Remotion (React motion graphics, see video/)."""
import json
import os
import shutil
import subprocess

from .util import ROOT, log

VIDEO = ROOT / "video"
RUN_DIR = VIDEO / "public" / "run"


def reset_run_dir() -> str:
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return str(RUN_DIR)


def render(props: dict, out_path: str) -> None:
    props_path = RUN_DIR / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    cmd = ["npx", "remotion", "render", "src/index.ts", "NewsShort", os.path.abspath(out_path),
           f"--props={props_path}", "--crf=19", f"--concurrency={os.cpu_count() or 2}", "--log=warn"]
    chrome = os.environ.get("CHROME_PATH") or shutil.which("google-chrome")
    if chrome:
        cmd.append(f"--browser-executable={chrome}")
    log("  rendering with Remotion…")
    subprocess.run(cmd, cwd=VIDEO, check=True)
    log(f"  video ready: {out_path} ({props['duration']:.1f}s)")
