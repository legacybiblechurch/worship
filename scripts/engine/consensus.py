"""Decide each line from the evidence, and say how sure we are and why."""
from __future__ import annotations

import difflib
import re

from norm import key, sim, tidy_display

CORROBORATE_ONLY = {"asr_prompted"}         # may join a cluster, may not start a disagreement
TRUSTED = {"library", "verified_recording", "captions_manual"}
HALLUCINATION = re.compile(r"guitar solo|instrumental|\bmusic\b|applause|\[|♪|subtitles|thank you for watching", re.I)


def _near_homophone(a: str, b: str) -> bool:
    """Do these two renderings differ only by sound-alike words? ('anchor'/'anger',
    'wood'/'food', 'loving'/'lovingkindness'). Compared letter-wise, ignoring spaces."""
    ka, kb = key(a).replace(" ", ""), key(b).replace(" ", "")
    if not ka or not kb:
        return False
    return difflib.SequenceMatcher(None, ka, kb, autojunk=False).ratio() >= 0.74

AGREE = 0.86          # candidates at least this similar are "the same words"
VERIFIED_CONF = 0.80
CHECK_MARGIN = 0.30   # a runner-up within this much of the winner is a real ambiguity


def _cluster(cands: list[tuple[str, str, float]]):
    """[(source, text, score)] -> [{text, sources, score}] merged by similarity."""
    clusters: list[dict] = []
    for src, text, score in cands:
        for c in clusters:
            if sim(c["text"], text) >= AGREE:
                c["sources"].append(src); c["score"] += score
                # prefer the best-cased/punctuated rendering as the display text
                if _display_rank(src) > _display_rank(c["lead"]):
                    c["text"], c["lead"] = text, src
                break
        else:
            clusters.append({"text": text, "lead": src, "sources": [src], "score": score})
    clusters.sort(key=lambda c: -c["score"])
    return clusters


def _display_rank(src: str) -> int:
    return {"verified_recording": 5, "library": 4, "captions_manual": 3, "asr_large": 2,
            "asr_prompted": 2, "asr_turbo": 1, "captions_auto": 1}.get(src, 0)


def _kinds(sources: list[str]) -> set[str]:
    return {s.split("_")[0] for s in sources}


def _late_library(sp_text: str, lib_cues: list[dict]) -> dict | None:
    """The DP could not place this line, but if what the listens heard is a
    sound-alike of some library line, that line is still a witness here."""
    best, bs = None, 0.0
    for ci, c in enumerate(lib_cues):
        s = sim(sp_text, c["text"])
        if s < 0.9:
            ka, kb = key(sp_text).replace(" ", ""), key(c["text"]).replace(" ", "")
            if ka and kb:
                s = max(s, difflib.SequenceMatcher(None, ka, kb, autojunk=False).ratio() - 0.06)
        if s > bs:
            best, bs = c, s
    if best and bs >= 0.72:
        return {"text": best["text"], "cue": None, "conf": best.get("conf", 0.95), "label": best.get("label"),
                "block": best.get("block"), "coverage": 1.0, "nsp": 0.0}
    return None


def decide(spine: list[dict], projections: dict[str, list], weights: dict[str, float], lib_cues: list | None = None) -> list[dict]:
    """projections: source name -> per-line projection (from align.project)."""
    lines = []
    for li, sp in enumerate(spine):
        cands = []
        total = 0.0
        if lib_cues and "library" in projections and projections["library"][li] is None:
            late = _late_library(sp["text"], lib_cues)
            if late:
                projections["library"][li] = late
        for name, proj in projections.items():
            p = proj[li]
            if not p or not p["text"].strip():
                continue
            w = weights.get(name, 0.5)
            if name.startswith("asr"):
                w *= max(0.3, min(1.0, p.get("conf", 0.6) + 0.2))
            if p.get("coverage", 1) < 0.5:
                w *= 0.6
            cands.append((name, p["text"], w)); total += w
        if not cands:
            lines.append({"text": sp["text"], "t0": sp["t0"], "t1": sp["t1"], "conf": 0.2,
                          "status": "unverified", "alts": [], "why": "only the primary listen heard this",
                          "sources": {}})
            continue
        clusters = _cluster(cands)
        # a cluster backed only by the corroborating pass cannot win or dissent
        strong = [c for c in clusters if set(c["sources"]) - CORROBORATE_ONLY]
        if strong:
            clusters = strong
        best = clusters[0]
        conf = best["score"] / total if total else 0
        kinds = _kinds(best["sources"])
        why = []
        if len(kinds) >= 2:
            conf = min(1.0, conf + 0.12); why.append("independent sources agree")
        elif len(best["sources"]) >= 2:
            why.append("two listens agree")
        else:
            why.append("one witness only")
        status = "verified"
        alts = []
        runner = clusters[1] if len(clusters) > 1 else None
        disagree = bool(runner) and runner["score"] >= best["score"] - CHECK_MARGIN * total and runner["score"] > 0.25 * total
        best_trusted = bool(set(best["sources"]) & TRUSTED)
        runner_trusted = bool(runner) and bool(set(runner["sources"]) & TRUSTED)
        resolved = False
        others = [c for c in clusters if c is not best]
        if best_trusted and others and not any(set(c["sources"]) & TRUSTED for c in others):
            # verified words vs listens only. Sound-alikes are how ASR fails; if every
            # dissenting listen is a sound-alike of the verified words, that settles it.
            if all(_near_homophone(best["text"], c["text"]) for c in others) or len(best["sources"]) >= 2:
                resolved = True; conf = max(conf, 0.85)
                why.append("listens misheard a sound-alike; verified words stand")
        elif runner_trusted and not best_trusted and _near_homophone(best["text"], runner["text"]):
            best, runner = runner, best
            resolved = True; conf = max(conf, 0.85)
            why.append("sound-alike resolved by verified words")
        if resolved:
            status = "verified"
        elif disagree:
            status = "check"; why.append("sources disagree")
            alts = [{"text": tidy_display(c["text"]), "sources": c["sources"]} for c in clusters[:3] if c is not best][:2]
        elif conf < VERIFIED_CONF or len(best["sources"]) == 1:
            if best_trusted and len(best["sources"]) >= 2:
                status = "verified"
            elif not best_trusted and len(best["sources"]) == 1 and conf < 0.5 and len(clusters) == 1:
                # one low-confidence listen, nobody else heard anything: a fade, a breath,
                # an ad-lib under the music. Not a congregation line; kept in the report.
                status = "excluded"; why.append("faint, one listen only")
            else:
                status = "check" if (len(clusters) > 1) else "unverified"
                if status == "unverified":
                    why.append("not enough evidence")
        if HALLUCINATION.search(best["text"]) and not best_trusted:
            status = "excluded"; why.append("instrumental/noise heard as words")
        lines.append({"text": tidy_display(best["text"]), "t0": sp["t0"], "t1": sp["t1"],
                      "conf": round(conf, 2), "status": status, "alts": alts, "why": "; ".join(why),
                      "sources": {n: t for n, t, _ in cands},
                      "label": _majority([projections[n][li].get("label") for n in projections
                                          if n == "library" and projections[n][li]]),
                      "block": _majority([projections[n][li].get("block") for n in projections
                                          if n == "library" and projections[n][li]])})
    return lines


def _majority(vals):
    vals = [v for v in vals if v is not None]
    return max(set(vals), key=vals.count) if vals else None


def vote_repeats(lines: list[dict]) -> list[dict]:
    """A chorus sung four times is four witnesses to the same words. Unify
    near-identical lines to the majority rendering and raise their confidence;
    a lone odd occurrence becomes a check with the majority as the alternative."""
    groups: list[list[int]] = []
    for i, ln in enumerate(lines):
        for g in groups:
            if sim(lines[g[0]]["text"], ln["text"]) >= 0.78:
                g.append(i); break
        else:
            groups.append([i])
    for g in groups:
        if len(g) < 2:
            continue
        texts = [key(lines[i]["text"]) for i in g]
        maj = max(set(texts), key=texts.count)
        n_maj = texts.count(maj)
        maj_display = next(lines[i]["text"] for i in g if key(lines[i]["text"]) == maj)
        for i in g:
            ln = lines[i]
            if key(ln["text"]) == maj:
                if n_maj >= 2 and ln["status"] != "check":
                    ln["conf"] = round(min(1.0, ln["conf"] + 0.1 * (n_maj - 1)), 2)
                    ln["why"] += f"; sung {len(g)}x, {n_maj} agree"
                    if ln["conf"] >= VERIFIED_CONF:
                        ln["status"] = "verified"
            else:
                if n_maj >= 2 and n_maj > len(g) - n_maj:
                    # minority rendering: adopt majority, keep own as the alternative
                    ln["alts"] = [{"text": ln["text"], "sources": ["this occurrence"]}] + ln.get("alts", [])
                    ln["text"] = maj_display
                    ln["status"] = "check" if ln["conf"] < 0.7 else "verified"
                    ln["why"] += f"; matched to {n_maj} other occurrences"
    return lines
