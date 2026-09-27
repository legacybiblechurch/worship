"""
Turn whatever a person typed in the Sheet's "Song" cell into a library slug.

Accepts: an exact slug, an exact/near title, or a loose phrase ("before the throne").
Returns (slug, matched_title, is_new).  is_new=True means it is not in the library yet
and the caller should treat it as a brand-new song (slug is a fresh slugified guess).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from lib_songs import load_songs

_ENTITY = {"&rsquo;": "'", "&amp;": "&", "&nbsp;": " ", "&#39;": "'", "&quot;": '"'}


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    for k, v in _ENTITY.items():
        s = s.replace(k, v)
    return s


def slugify(text: str) -> str:
    text = _clean(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "untitled"


def _norm(text: str) -> str:
    """comparison key: lowercase alnum words only"""
    return re.sub(r"[^a-z0-9 ]", "", _clean(text).lower()).strip()


def resolve(query: str) -> tuple[str, str, bool]:
    q = query.strip()
    if not q:
        raise ValueError("empty song")

    songs = load_songs()
    by_norm_title = {_norm(s["title"]): slug for slug, s in songs.items()}

    qslug = slugify(q)
    if qslug in songs:
        return qslug, songs[qslug]["title"], False

    qn = _norm(q)
    if qn in by_norm_title:
        slug = by_norm_title[qn]
        return slug, songs[slug]["title"], False

    # fuzzy: best ratio over titles and slugs
    best_slug, best_score = None, 0.0
    for slug, s in songs.items():
        score = max(
            SequenceMatcher(None, qn, _norm(s["title"])).ratio(),
            SequenceMatcher(None, qslug, slug).ratio(),
        )
        # containment bonus — "before the throne" in "before the throne of god above"
        if qn and qn in _norm(s["title"]):
            score = max(score, 0.9)
        if score > best_score:
            best_slug, best_score = slug, score

    if best_score >= 0.72:
        return best_slug, songs[best_slug]["title"], False

    # not in the library
    return qslug, q, True


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        slug, title, is_new = resolve(arg)
        tag = "NEW" if is_new else "lib"
        print(f"{arg!r:45} -> [{tag}] {slug}  ({title})")
