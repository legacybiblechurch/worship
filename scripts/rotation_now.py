#!/usr/bin/env python3
"""Who is up this coming Sunday, as a tiny JSON file the phone can read.

Reads js/rotation-data.js (the same rules rotation.html uses) and writes
rotation/now.json:

  {"sunday": "2026-11-16", "label": "Sunday, November 16",
   "slides": "Quaid", "stream": "Cole", "table": "Michael", "off": false, "note": "",
   "guide": "<Drive folder>"}

The Wednesday text on Quaid's iPhone fetches this and messages the three names.
Run by .github/workflows/rotation-now.yml every morning and whenever the data
file changes. Nothing to install; standard library only.
"""
from __future__ import annotations
import json, re, sys, pathlib, datetime as dt
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "js" / "rotation-data.js"
OUT = ROOT / "rotation" / "now.json"


def load() -> dict:
    src = DATA.read_text(encoding="utf-8")
    m = re.search(r"window\.LBC_ROTATION\s*=\s*(\{.*\});?\s*$", src, re.S)
    if not m:
        sys.exit("rotation-data.js: could not find the object")
    return json.loads(m.group(1))


def coming_sunday(today: dt.date) -> dt.date:
    return today + dt.timedelta(days=(6 - today.weekday()) % 7)   # Monday=0 ... Sunday=6


def who(cfg: dict, sunday: dt.date) -> dict:
    people = cfg.get("people", [])
    n = len(people)
    start = dt.date.fromisoformat(cfg["start"])
    weeks = round((sunday - start).days / 7)
    jobs = cfg.get("jobs") or {"slides": 0, "stream": 1, "table": 3}
    out = {"sunday": sunday.isoformat(), "label": sunday.strftime("%A, %B %-d"),
           "slides": "", "stream": "", "table": "", "off": False, "note": "", "guide": cfg.get("guide", "")}
    if n:
        i = weeks % n
        for job, off in jobs.items():
            out[job] = people[(i + int(off)) % n]
    ch = (cfg.get("changes") or {}).get(sunday.isoformat())
    if ch:
        if ch.get("off"):
            out["off"] = True
        for job in jobs:
            if ch.get(job):
                out[job] = ch[job]
        if ch.get("note"):
            out["note"] = ch["note"]
    # the Wednesday texts, word for word. Change them here and the phone sends the new words next week.
    site = "worship.legacybiblechurch.com"
    out["msg_slides"] = f"Hey {out['slides']}, reminder that you'll be handling the worship guide and slides this Sunday. Here's everything you'll need: https://{site}/jobs/slides/"
    out["msg_stream"] = f"Hey {out['stream']}, reminder that you'll be handling the livestream this Sunday. Here's everything you'll need: https://{site}/jobs/stream/"
    out["msg_table"] = f"Hey {out['table']}, reminder that you'll be handling the Lord's Table this Sunday. Here's everything you'll need: https://{site}/jobs/table/"
    return out


def main() -> None:
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if len(sys.argv) > 1:
        today = dt.date.fromisoformat(sys.argv[1])
    data = who(load(), coming_sunday(today))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print("unchanged:", data["sunday"], data["slides"], data["stream"], data["table"])
        return
    OUT.write_text(text, encoding="utf-8")
    print("wrote:", data["sunday"], data["slides"], data["stream"], data["table"])


if __name__ == "__main__":
    main()
