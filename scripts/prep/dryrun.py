"""
Local end-to-end check WITHOUT the Google Sheet or the YouTube Data API.

Give it slugs already in the library; it fetches the transcript for each song's
existing `youtube:` URL, reconciles against the library lyrics, and prints a
before/after plus a draft JSON to drafts/<slug>.json.

    ANTHROPIC_API_KEY=... python3 dryrun.py before-the-throne-of-god-above \
        how-deep-the-fathers-love-for-us gladly-would-i-leave-behind-me

Needs: yt-dlp on PATH, ANTHROPIC_API_KEY. GROQ_API_KEY optional (audio fallback).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import lib_songs
import reconcile as rec
from transcript import fetch_transcript

DRAFTS = Path(__file__).resolve().parents[2] / "drafts"


def show_blocks(blocks: list[dict]) -> str:
    out = []
    for b in blocks:
        out.append(f'  [{b.get("label", "")}]')
        out.extend(f"    {ln}" for ln in b["lines"])
    return "\n".join(out)


def main(slugs: list[str]) -> None:
    songs = lib_songs.load_songs()
    allow_audio = bool(os.environ.get("GROQ_API_KEY"))
    DRAFTS.mkdir(exist_ok=True)

    for slug in slugs:
        if slug not in songs:
            print(f"\n!! {slug} not in library\n")
            continue
        song = songs[slug]
        print(f"\n{'=' * 72}\n{song['title']}  ({slug})\n{song['youtube']}\n{'=' * 72}")

        tr = fetch_transcript(song["youtube"], allow_audio=allow_audio)
        if not tr:
            print("  no transcript available")
            continue
        print(f'  transcript: source={tr["source"]}  cues={len(tr["cues"])}')

        r = rec.reconcile(song["title"], song["lyrics"], tr)
        print(f'\n  confidence: {r["confidence"]}     order: {r["order"]}')
        print(f'  notes: {r["notes"]}\n')
        print("  --- REFERENCE (library) ---")
        print(show_blocks(song["lyrics"]))
        print("\n  --- RECONCILED (this video) ---")
        print(show_blocks(r["lyrics"]))

        draft = {
            "slug": slug, "title": song["title"], "input": slug, "isNew": False,
            "forced": None, "signature": "dryrun",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "candidates": [{
                "videoId": song["youtube"].split("v=")[-1][:11],
                "url": song["youtube"], "title": song["title"], "channel": "",
                "duration": "", "durationSec": 0, "views": 0, "hasCaptions": True,
                "transcriptSource": tr["source"], "lyrics": r["lyrics"],
                "confidence": r["confidence"], "notes": r["notes"], "order": r["order"],
            }],
        }
        (DRAFTS / f"{slug}.json").write_text(json.dumps(draft, indent=2, ensure_ascii=False))
        print(f"\n  wrote drafts/{slug}.json")


if __name__ == "__main__":
    args = sys.argv[1:] or [
        "before-the-throne-of-god-above",
        "how-deep-the-fathers-love-for-us",
        "gladly-would-i-leave-behind-me",
    ]
    main(args)
