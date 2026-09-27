"""
Map each drafted lyric line back to the moment it is sung in the video.

The transcript we already fetched is a list of timestamped cues
(`{"t": seconds, "text": ...}`). The drafted lyrics are the cleaned-up,
slide-ordered version of the same words. Matching one to the other gives every
line a timestamp, which is what lets the prep page do "click a line, the video
jumps there" - so a reviewer spot-checks four places instead of sitting through
the whole song twice.

Deliberately deterministic: no model involved, so it can't invent a timestamp.
A line it can't find in the recording gets `None`, which is itself the useful
signal - it means "these words were never heard in this video", i.e. exactly
the line a human should look at.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")

# how far ahead of the cursor to look for a match, in cues
_WINDOW = 40
# a line has to share this fraction of its words with the cues to count as found
_THRESHOLD = 0.6
# a line can span this many consecutive cues (ASR splits mid-phrase constantly)
_MAX_SPAN = 3


def _tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    s = s.replace("'", "'").replace("’", "'").replace("'", "")
    s = _PUNCT.sub(" ", s)
    return [t for t in _WS.sub(" ", s).strip().split(" ") if t]


def _overlap(line_tokens: list[str], window_tokens: list[str]) -> float:
    """Fraction of the line's words present in the cue window (multiset-aware)."""
    if not line_tokens:
        return 0.0
    have = Counter(window_tokens)
    hit = 0
    for tok in line_tokens:
        if have[tok] > 0:
            have[tok] -= 1
            hit += 1
    return hit / len(line_tokens)


def align(lines: list[str], cues: list[dict]) -> list[float | None]:
    """Returns one timestamp (seconds) per line, or None where not found.

    Walks forward only. Lyrics are in performance order and cues are in time
    order, so a forward cursor stops a repeated chorus from matching back to
    its first occurrence - each repeat lands on its own moment in the video.
    """
    if not lines or not cues:
        return [None] * len(lines)

    cue_tokens = [_tokens(c.get("text", "")) for c in cues]
    out: list[float | None] = []
    cursor = 0

    for line in lines:
        lt = _tokens(line)
        if not lt:
            out.append(None)
            continue

        best_score, best_idx, best_end = 0.0, -1, -1
        for i in range(cursor, min(cursor + _WINDOW, len(cues))):
            window: list[str] = []
            for span in range(_MAX_SPAN):
                if i + span >= len(cues):
                    break
                window = window + cue_tokens[i + span]
                score = _overlap(lt, window)
                if score > best_score:
                    best_score, best_idx, best_end = score, i, i + span
                if score >= 0.999:          # exact - stop widening
                    break
            if best_score >= 0.999:         # and stop scanning
                break

        if best_idx >= 0 and best_score >= _THRESHOLD:
            # the match may span several cues, and the line's own words may not
            # start in the first of them - seek forward to the cue the line
            # actually begins in, so the video jumps to the right moment
            want = set(lt)
            start = best_idx
            while start < best_end and not (want & set(cue_tokens[start])):
                start += 1
            out.append(round(float(cues[start].get("t", 0)), 1))
            cursor = start + 1
        else:
            out.append(None)

    return out


def annotate(lyrics: list[dict], cues: list[dict]) -> list[dict]:
    """Add a `times` array (same length as `lines`) to each lyric block.

    Kept as a parallel array rather than turning each line into an object so
    that every existing consumer - the library, Control, Display, the hymnal -
    reads `lines` exactly as before and simply ignores `times`.
    """
    if not cues:
        return lyrics
    flat = [ln for b in lyrics for ln in (b.get("lines") or [])]
    times = align(flat, cues)
    out, i = [], 0
    for b in lyrics:
        n = len(b.get("lines") or [])
        blk = dict(b)
        blk["times"] = times[i:i + n]
        out.append(blk)
        i += n
    return out


def strip_times(lyrics: list[dict]) -> list[dict]:
    """Drop timestamps before anything is written to the permanent library.

    Timestamps belong to one specific recording; the library entry outlives any
    particular video, so keeping them there would just be a lie waiting to
    happen if the video is ever swapped.
    """
    return [{k: v for k, v in b.items() if k != "times"} for b in (lyrics or [])]
