"""Group lines into slides/sections in performance order, and label them."""
from __future__ import annotations

from norm import key, sim

BLOCK_GAP = 2.4   # seconds of silence that separates sections


def blocks(lines: list[dict]) -> list[dict]:
    if not lines:
        return []
    out, cur = [], [lines[0]]
    for prev, ln in zip(lines, lines[1:]):
        gap = (ln["t0"] or 0) - (prev["t1"] or 0)
        new_lib_block = (ln.get("block") is not None and prev.get("block") is not None
                         and ln["block"] != prev["block"])
        if gap >= BLOCK_GAP or new_lib_block or len(cur) >= 8:
            out.append(cur); cur = [ln]
        else:
            cur.append(ln)
    out.append(cur)
    return [{"lines": b} for b in out]


def label(blks: list[dict], library_labels: list[str] | None = None) -> list[dict]:
    """Inherit library labels where the block aligned to a library block; otherwise
    detect repeats (Chorus / Refrain) and number the rest as verses."""
    sig = [" | ".join(key(l["text"]) for l in b["lines"]) for b in blks]
    # repeated blocks (by similarity) -> chorus
    rep = [False] * len(blks)
    for i in range(len(blks)):
        for j in range(len(blks)):
            if i != j and sim(sig[i], sig[j]) >= 0.8 and len(blks[i]["lines"]) >= 2:
                rep[i] = True
    verse = 0
    for i, b in enumerate(blks):
        lib = [l.get("label") for l in b["lines"] if l.get("label")]
        if lib:
            b["label"] = max(set(lib), key=lib.count)
            continue
        if rep[i]:
            b["label"] = "Chorus"
        elif len(b["lines"]) == 1:
            b["label"] = "Tag"
        else:
            verse += 1
            b["label"] = f"Verse {verse}"
    return blks
