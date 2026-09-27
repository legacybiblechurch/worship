"""
Read the worship setlist from the published Google Sheet (CSV export).

New layout (header row, any column order):
    Song | Video | Review | Fixes
      - Song   : free text the person typed (title / slug / phrase)      [required]
      - Video  : optional YouTube URL to force a specific video
      - Review : blank | "Approve" | "Redo"   (set by the person)
      - Fixes  : optional free-text corrections for the reconcile step

Old layout (no header, one slug per row) is still accepted so nothing breaks
mid-migration: each non-empty line becomes a row with Song=<line>.
"""

from __future__ import annotations

import csv
import io
import os
import urllib.request
from dataclasses import dataclass, field

# override with a URL or a local file path for testing: LBC_SHEET_CSV=./test.csv
PUB_CSV = os.environ.get("LBC_SHEET_CSV") or (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSBczlDX3xoDhPZdmURMEmduM_"
    "s1lYvPZiRovZ-ObHroIEsnJ9u1D813GaRlLK6Q9NsDpOTtL4UaRnu/pub?gid=0&single=true&output=csv"
)

_KNOWN = {"song", "video", "review", "fixes"}


@dataclass
class Row:
    song: str
    video: str = ""
    review: str = ""
    fixes: str = ""
    # filled in by the pipeline
    slug: str = ""
    title: str = ""
    is_new: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.review.strip().lower() in ("approve", "approved", "yes", "y", "✓")

    @property
    def redo(self) -> bool:
        return self.review.strip().lower() in ("redo", "again", "regenerate")


def _fetch(url: str) -> str:
    if not url.startswith("http"):
        with open(url, encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "lbc-worship-prep"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_csv(text: str) -> list[Row]:
    reader = list(csv.reader(io.StringIO(text)))
    reader = [r for r in reader if any(c.strip() for c in r)]
    if not reader:
        return []

    header = [c.strip().lower() for c in reader[0]]
    has_header = bool(_KNOWN & set(header))

    rows: list[Row] = []
    if has_header:
        idx = {name: header.index(name) for name in _KNOWN if name in header}
        # a published sheet sometimes drops a header cell (e.g. "Fixes" comes back
        # blank) - fill any missing column positionally from the Song column
        base = idx.get("song", 0)
        for off, name in enumerate(("song", "video", "review", "fixes")):
            idx.setdefault(name, base + off)

        def cell(r, name):
            i = idx.get(name)
            return r[i].strip() if i is not None and 0 <= i < len(r) else ""

        for r in reader[1:]:
            song = cell(r, "song")
            if not song:
                continue
            rows.append(Row(song=song, video=cell(r, "video"),
                            review=cell(r, "review"), fixes=cell(r, "fixes")))
    else:
        for r in reader:
            first = r[0].strip()
            if first:
                rows.append(Row(song=first))
    return rows


def load(url: str = PUB_CSV) -> list[Row]:
    return parse_csv(_fetch(url))


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else PUB_CSV
    data = open(src).read() if not src.startswith("http") else _fetch(src)
    for row in parse_csv(data):
        print(row)
