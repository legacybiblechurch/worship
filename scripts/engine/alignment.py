"""Turn timed ASR into a line 'spine', then project every other witness onto it.

The spine is the sequence of sung lines in performance order, each with a time
range. Every source is aligned to the spine's word stream (global sequence
alignment on normalised tokens), so for each spine line we know what each
witness said there. Untimed library lines get the same treatment, which also
tells us which library lines were actually sung and in what order.
"""
from __future__ import annotations

import difflib

from norm import tokens, tidy_display

MAX_WORDS = 11        # a congregation line longer than this is two lines
GAP_SPLIT = 0.75      # seconds of silence inside a segment that ends a line


def build_spine(asr) -> list[dict]:
    """asr: Source with word-timed cues -> [{t0,t1,text,words,conf}] lines."""
    lines = []
    for cue in asr.cues:
        words = cue.get("words") or []
        if not words:
            lines.append({"t0": cue["t0"], "t1": cue["t1"], "text": cue["text"], "words": [], "conf": cue["conf"]})
            continue
        # split points: big pauses, sentence punctuation, or length
        cur = []
        for i, w in enumerate(words):
            cur.append(w)
            end = (i == len(words) - 1)
            gap = (words[i + 1]["t0"] - w["t1"]) if not end else 0
            punct = w["w"].strip().endswith((".", "?", "!", ";", ","))
            if end or gap >= GAP_SPLIT or (punct and len(cur) >= 4) or len(cur) >= MAX_WORDS:
                lines.append({"t0": cur[0]["t0"], "t1": cur[-1]["t1"],
                              "text": " ".join(x["w"].strip() for x in cur),
                              "words": cur, "conf": cue["conf"]})
                cur = []
    # merge tiny fragments (1-2 words) into their neighbour
    merged = []
    for ln in lines:
        if merged and len(tokens(ln["text"])) <= 2 and (ln["t0"] - merged[-1]["t1"]) < 1.0:
            m = merged[-1]
            m["text"] += " " + ln["text"]; m["t1"] = ln["t1"]; m["words"] += ln["words"]
        else:
            merged.append(ln)
    for ln in merged:
        ln["text"] = tidy_display(ln["text"])
    return merged


def _stream(cues):
    """(tokens, owner index per token, original words per token) for a source."""
    toks, owner, orig = [], [], []
    for ci, c in enumerate(cues):
        ws = c.get("words")
        if ws:
            for w in ws:
                for t in tokens(w["w"]):
                    toks.append(t); owner.append(ci); orig.append(w["w"].strip())
        else:
            raw = str(c["text"]).split()
            for w in raw:
                for t in tokens(w):
                    toks.append(t); owner.append(ci); orig.append(w)
    return toks, owner, orig


def project(spine: list[dict], source) -> list[dict | None]:
    """For each spine line, what this source says there (or None if it has
    nothing aligned to that stretch). Also returns library line ownership."""
    sp_toks, sp_owner, _ = _stream([{"text": l["text"], "words": l["words"]} for l in spine])
    src_toks, src_owner, src_orig = _stream(source.cues)
    if not sp_toks or not src_toks:
        return [None] * len(spine)

    # which source tokens land on which spine line
    hit: list[list[int]] = [[] for _ in spine]
    sm = difflib.SequenceMatcher(None, sp_toks, src_toks, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or tag == "replace":
            # distribute src tokens across the spine tokens they replace/equal
            span = max(1, i2 - i1)
            for k, j in enumerate(range(j1, j2)):
                i = i1 + min(span - 1, int(k * span / max(1, j2 - j1)))
                hit[sp_owner[i]].append(j)
        elif tag == "insert":
            # extra words the spine lacks: attach to the line they follow
            i = min(i1, len(sp_owner) - 1) if i1 < len(sp_owner) else len(sp_owner) - 1
            if i1 > 0:
                i = i1 - 1
            hit[sp_owner[i]].extend(range(j1, j2))
        # 'delete' = spine has words this source lacks; nothing to attach

    out = []
    for li in range(len(spine)):
        js = sorted(set(hit[li]))
        if not js:
            out.append(None); continue
        # a source line is the ORIGINAL words of its tokens, in order; and the
        # library cue (block/label) that most of those tokens came from
        words = [src_orig[j] for j in js]
        owners = [src_owner[j] for j in js]
        top = max(set(owners), key=owners.count)
        cue = source.cues[top]
        cov = len(js) / max(1, len(tokens(spine[li]["text"])))
        out.append({"text": " ".join(words), "cue": top, "conf": cue.get("conf", 0.5),
                    "label": cue.get("label"), "block": cue.get("block"), "coverage": round(cov, 2),
                    "nsp": cue.get("nsp", 0.0)})
    return out


# ─────────────────────────────────────────── library-guided segmentation
#
# The library lists a chorus once; the recording sings it four times. A global
# alignment can't map one to four, and pause-based lines split where the singer
# breathed, not where the congregation line ends. So when we have the song's
# verified lines, we segment the performance's word stream INTO those lines:
# a dynamic programme over the ASR words where each step either matches a
# library line (repeats allowed, any order) or takes an "unknown" chunk (a line
# this performance sings that the library doesn't have).

from norm import sim as _sim  # noqa: E402

UNKNOWN_COST = 0.45     # per word; a library match wins whenever sim > ~0.5
LEN_PENALTY = 0.50      # per word of length mismatch, so a match can't swallow neighbours
MIN_MATCH = 0.55        # below this a "match" is really an unknown chunk


def segment_by_library(words: list[dict], lib) -> list[dict]:
    """words: ASR word dicts in order (w,t0,t1). lib: library Source.
    Returns spine lines with .lib (library cue index) where matched."""
    toks = [tokens(w["w"]) for w in words]
    flat, owner = [], []
    for i, ts in enumerate(toks):
        for t in ts:
            flat.append(t); owner.append(i)
    n = len(flat)
    lib_lines = [(ci, tokens(c["text"])) for ci, c in enumerate(lib.cues)]
    lib_lines = [(ci, t) for ci, t in lib_lines if t]
    INF = float("inf")
    best = [INF] * (n + 1); back = [None] * (n + 1)
    best[0] = 0.0
    for i in range(1, n + 1):
        # unknown chunk of 1..11 tokens
        for k in range(1, min(11, i) + 1):
            c = best[i - k] + UNKNOWN_COST * k
            if c < best[i]:
                best[i], back[i] = c, (i - k, None)
        # a library line, allowing a couple of words' slack either way
        for ci, lt in lib_lines:
            m = len(lt)
            for k in range(max(1, m - 2), min(i, m + 2) + 1):
                seg = flat[i - k:i]
                s = difflib.SequenceMatcher(None, seg, lt, autojunk=False).ratio()
                if s < 0.9:
                    # letters only: compound spellings and sound-alike mishearings
                    cs = difflib.SequenceMatcher(None, "".join(seg), "".join(lt), autojunk=False).ratio()
                    s = max(s, cs - 0.08)
                if s < MIN_MATCH:
                    continue
                c = best[i - k] + (1.0 - s) * m + 0.15 + LEN_PENALTY * abs(k - m)
                if c < best[i]:
                    best[i], back[i] = c, (i - k, ci)
    # walk back
    cuts = []
    i = n
    while i > 0:
        j, ci = back[i]
        cuts.append((j, i, ci)); i = j
    cuts.reverse()
    # merge adjacent unknown chunks into natural lines (pause/length based)
    lines = []
    for j, i, ci in cuts:
        wi0, wi1 = owner[j], owner[i - 1]
        ws = words[wi0:wi1 + 1]
        text = " ".join(w["w"].strip() for w in ws)
        ln = {"t0": ws[0]["t0"], "t1": ws[-1]["t1"], "text": tidy_display(text), "words": ws,
              "conf": 0.6, "lib": ci}
        if ci is None and lines and lines[-1]["lib"] is None and \
                (ln["t0"] - lines[-1]["t1"]) < GAP_SPLIT and len(tokens(lines[-1]["text"] + " " + text)) <= MAX_WORDS:
            m = lines[-1]
            m["text"] = tidy_display(m["text"] + " " + text); m["t1"] = ln["t1"]; m["words"] += ws
        else:
            lines.append(ln)
    _prefer_contiguous(lines, lib)
    return lines


def _prefer_contiguous(lines, lib):
    by_key = {}
    for ci, c in enumerate(lib.cues):
        by_key.setdefault(" ".join(tokens(c["text"])), []).append(ci)
    for idx, ln in enumerate(lines):
        ci = ln.get("lib")
        if ci is None:
            continue
        twins = by_key.get(" ".join(tokens(lib.cues[ci]["text"])), [])
        if len(twins) < 2:
            continue
        neigh = [lines[j].get("lib") for j in (idx - 1, idx + 1) if 0 <= j < len(lines)]
        nblocks = {lib.cues[n]["block"] for n in neigh if n is not None}
        for t in twins:
            if lib.cues[t]["block"] in nblocks:
                ln["lib"] = t
                break


def library_projection(spine: list[dict], lib) -> list[dict | None]:
    """When the spine came from segment_by_library, the library's word for each
    line is simply the matched cue (its text, label and block)."""
    out = []
    for ln in spine:
        ci = ln.get("lib")
        if ci is None:
            out.append(None); continue
        c = lib.cues[ci]
        out.append({"text": c["text"], "cue": ci, "conf": c.get("conf", 0.95), "label": c.get("label"),
                    "block": c.get("block"), "coverage": 1.0, "nsp": 0.0})
    return out


def self_library(lines: list[dict]):
    """Blind mode: the recording's own repeats are a library. Any line sung at
    least twice (by similarity) becomes a reference line, so every occurrence
    of a chorus is cut the same way."""
    from sources import Source
    reps = []
    for i, a in enumerate(lines):
        if any(_sim(a["text"], r) >= 0.8 for r in reps):
            continue
        if sum(1 for b in lines if _sim(a["text"], b["text"]) >= 0.8) >= 2 and len(tokens(a["text"])) >= 3:
            reps.append(a["text"])
    if not reps:
        return None
    return Source("self", "self", 0.0, [{"t0": None, "t1": None, "text": t, "conf": 0.6} for t in reps])


def split_long(lines: list[dict], max_words: int = 8) -> list[dict]:
    """A blind line longer than a congregation line is cut at its biggest pause,
    else at a comma, else in the middle."""
    out = []
    for ln in lines:
        ws = ln.get("words") or []
        if len(tokens(ln["text"])) <= max_words or len(ws) < 4:
            out.append(ln); continue
        gaps = [(ws[i + 1]["t0"] - ws[i]["t1"], i) for i in range(len(ws) - 1)]
        commas = [i for i, w in enumerate(ws[:-1]) if w["w"].strip().endswith((",", ";"))]
        mid = len(ws) // 2
        g, gi = max(gaps)
        if g >= 0.35 and 2 <= gi <= len(ws) - 3:
            cut = gi
        elif commas:
            cut = min(commas, key=lambda i: abs(i - mid))
        else:
            cut = mid - 1
        a, b = ws[:cut + 1], ws[cut + 1:]
        for part in (a, b):
            out.append({"t0": part[0]["t0"], "t1": part[-1]["t1"], "words": part, "conf": ln["conf"],
                        "text": tidy_display(" ".join(w["w"].strip() for w in part))})
    return out
