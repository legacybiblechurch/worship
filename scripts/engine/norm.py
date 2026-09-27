"""Text normalisation and comparison for lyric evidence.

Everything that compares two pieces of sung text goes through here, so a
comma, a capital, "O" vs "oh", or a curly apostrophe never counts as a
disagreement.
"""
from __future__ import annotations

import difflib
import re

_APOS = re.compile(r"[‘’ʼ`]")
_PUNCT = re.compile(r"[^\w\s']")
_WS = re.compile(r"\s+")

# sung variants that are the same word for our purposes
_EQUIV = {
    "oh": "o", "ohh": "o", "ooh": "o", "yeah": "yes", "yea": "yes",
    "thru": "through", "til": "till", "'til": "till", "until": "till",
    "ev'ry": "every", "evry": "every", "heav'n": "heaven", "heavn": "heaven",
    "pow'r": "power", "powr": "power", "o'er": "over", "oer": "over",
    "ne'er": "never", "neer": "never", "e'er": "ever", "eer": "ever",
    "saviour": "savior", "honour": "honor", "glorify": "glorify",
    "hallelujah": "alleluia", "halleluia": "alleluia", "allelujah": "alleluia",
    "calv'ry": "calvary", "calvry": "calvary",
}


def tokens(text: str) -> list[str]:
    """Lower-case word list with punctuation and spelling variants collapsed."""
    t = _APOS.sub("'", str(text or "")).lower()
    t = t.replace("-", " ")
    t = _PUNCT.sub(" ", t)
    out = []
    for w in _WS.split(t.strip()):
        if not w:
            continue
        w = w.strip("'")
        if not w:
            continue
        out.append(_EQUIV.get(w, w))
    return _destutter(out)


def _destutter(ws: list[str]) -> list[str]:
    """Drop an immediately repeated 1-3 word run (an ASR stutter), keeping the
    first copy. 'oh oh oh' style vocal repeats are left alone (single short word)."""
    i, out = 0, []
    while i < len(ws):
        dropped = False
        for n in (3, 2):        # never single words: "holy, holy, holy" is a lyric
            if i + 2 * n <= len(ws) and ws[i:i + n] == ws[i + n:i + 2 * n]:
                out.extend(ws[i:i + n]); i += 2 * n; dropped = True
                # swallow further copies of the same run
                while i + n <= len(ws) and ws[i:i + n] == out[-n:]:
                    i += n
                break
        if not dropped:
            out.append(ws[i]); i += 1
    return out


def key(text: str) -> str:
    return " ".join(tokens(text))


def sim(a: str, b: str) -> float:
    """0..1 similarity of two lines, on normalised tokens."""
    ta, tb = tokens(a), tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()


def wer(ref: str, hyp: str) -> float:
    """Word error rate of hyp against ref (0 = identical)."""
    r, h = tokens(ref), tokens(hyp)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (0 if r[i - 1] == h[j - 1] else 1))
            prev = cur
    return d[len(h)] / len(r)


def tidy_display(text: str) -> str:
    """Presentation text: straight apostrophes, no trailing full stop, capitalised."""
    t = _APOS.sub("'", str(text or "")).strip()
    t = _WS.sub(" ", t)
    t = re.sub(r"[.\s]+$", "", t)
    t = re.sub(r"\s+([,;:!?])", r"\1", t)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.8 * len(letters) and len(letters) > 6:
        t = t.lower()
        t = re.sub(r"\bi\b", "I", t)
        t = re.sub(r"\b(god|lord|jesus|christ|redeemer|savior|saviour|spirit|father)\b", lambda m: m.group(1).capitalize(), t)
    if t:
        t = t[0].upper() + t[1:]
    return t
