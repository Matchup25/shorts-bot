"""Which publishing slot (07:00 / 19:00 Zurich time…) the next Short is for.

GitHub starts scheduled runs late, or now and then not at all. So the workflow wakes up every
3 hours and this module decides whether a Short is due:
- a slot is filled at most AHEAD_HOURS early, so the news is still fresh when it goes live;
- a slot that was missed by less than LATE_HOURS is published right away instead of being lost;
- a slot already in data/history.json is never filled twice.

`python -m bot.slots` writes due=true/false for the workflow (it needs only PyYAML).
"""
import datetime as dt
import os
from zoneinfo import ZoneInfo

from .util import load_config, load_history, log

AHEAD_HOURS = 6
LATE_HOURS = 3


def _key(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slots(cfg: dict, now: dt.datetime) -> list:
    tz = ZoneInfo(cfg.get("timezone", "Europe/Zurich"))
    local = now.astimezone(tz)
    out = []
    for day in (-1, 0, 1, 2):
        date = (local + dt.timedelta(days=day)).date()
        for hhmm in cfg.get("publish_times") or []:
            h, m = (int(x) for x in str(hhmm).split(":"))
            out.append(dt.datetime(date.year, date.month, date.day, h, m, tzinfo=tz))
    return sorted(out)


def choose(cfg: dict, history: list, manual: bool, now: dt.datetime | None = None):
    """Return (slot, publish_at). `slot` is remembered in the history; `publish_at` is when YouTube
    should publish (None = right away). (None, None) means no Short is due now."""
    now = now or dt.datetime.now(dt.timezone.utc)
    taken = {h.get("slot") or h.get("publish_at") for h in history}
    ahead = dt.timedelta(hours=48 if manual else AHEAD_HOURS)
    for t in _slots(cfg, now):
        k = _key(t)
        if k in taken or t < now - dt.timedelta(hours=LATE_HOURS) or t > now + ahead:
            continue
        return k, (k if t > now + dt.timedelta(minutes=15) else None)
    return None, None


def is_manual() -> bool:
    return os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "schedule"


def uses_slots(cfg: dict) -> bool:
    """Test runs and runs with a chosen privacy publish right away, without slots."""
    if os.environ.get("DRY_RUN", "").lower() == "true" or os.environ.get("PRIVACY_OVERRIDE", "").strip():
        return False
    return bool(cfg.get("publish_times"))


if __name__ == "__main__":
    cfg = load_config()
    if not uses_slots(cfg):
        due, why = True, "test run or chosen privacy"
    else:
        slot, publish_at = choose(cfg, load_history(), is_manual())
        due = bool(slot)
        why = (f"slot {slot} UTC, " + ("scheduled" if publish_at else "publish right away")) if slot \
            else "no slot due in the next hours (or already filled)"
    log(f"Short due: {due} ({why})")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"due={'true' if due else 'false'}\n")
