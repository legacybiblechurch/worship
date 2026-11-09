#!/usr/bin/env python3
"""Who is up this coming Sunday, as a tiny JSON file the phone can read.

Reads js/rotation-data.js (the same rules rotation.html uses) and writes
rotation/now.json:

  {"sunday": "2026-11-16", "label": "Sunday, November 16",
   "slides": "Quaid", "table": "Marco", "off": false, "note": "",
   "guide": "<Drive folder>"}

The Wednesday text on Quaid's iPhone fetches this and messages the two names.
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
    out = {"sunday": sunday.isoformat(), "label": sunday.strftime("%A, %B %-d"),
           "slides": "", "table": "", "off": False, "note": "", "guide": cfg.get("guide", "")}
    if n:
        i = weeks % n
        out["slides"] = people[i]
        out["table"] = people[(i + int(cfg.get("tableOffset", 0))) % n]
    ch = (cfg.get("changes") or {}).get(sunday.isoformat())
    if ch:
        if ch.get("off"):
            out["off"] = True
        if ch.get("slides"):
            out["slides"] = ch["slides"]
        if ch.get("table"):
            out["table"] = ch["table"]
        if ch.get("note"):
            out["note"] = ch["note"]
    return out


def main() -> None:
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if len(sys.argv) > 1:
        today = dt.date.fromisoformat(sys.argv[1])
    data = who(load(), coming_sunday(today))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print("unchanged:", data["sunday"], data["slides"], data["table"])
        return
    OUT.write_text(text, encoding="utf-8")
    print("wrote:", data["sunday"], data["slides"], data["table"])


if __name__ == "__main__":
    main()
