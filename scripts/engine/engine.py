"""The Exact Lyrics Engine.

    analyze(video_url, slug=None, audio=None) -> result

Collects every witness it can reach (verified recording, captions, this
song's verified library words, several independent listens of the audio),
aligns them to the performance, decides each line by weighted agreement,
lets repeated sections vote, labels the structure, and reports:

    verdict   "verified" | "check" | "unverified"
    lyrics    [{label, lines}]         ready for the slide builder
    lines     [{text, t0, t1, conf, status, alts, why}]   per-line evidence
    checks    the handful of genuinely ambiguous lines, with timestamps
    report    what was available, what was missing, timings

Raw evidence is cached in evidence/<videoId>.json so re-running never
re-transcribes, and a human-confirmed result in verified/<videoId>.json
short-circuits everything.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# engine dir first (its own modules), then prep (lib_songs, transcript)
for p in (HERE.parent / "prep", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import alignment as align  # noqa: E402
import consensus  # noqa: E402
import sources as S  # noqa: E402
import structure  # noqa: E402
from norm import key, tidy_display  # noqa: E402

_VID = re.compile(r"(?:v=|/shorts/|youtu\.be/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def video_id(url: str) -> str:
    m = _VID.search(url or "")
    if m:
        return m.group(1)
    return url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") else ""


def _evidence_path(vid: str) -> Path:
    return REPO / "evidence" / f"{vid}.json"


def _load_evidence(vid: str) -> dict:
    p = _evidence_path(vid)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_evidence(vid: str, ev: dict) -> None:
    p = _evidence_path(vid)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(ev, ensure_ascii=False))


def _src_from_cache(name: str, blob: dict) -> S.Source:
    return S.Source(name, blob["kind"], S.WEIGHTS.get(name, 0.5), blob["cues"], blob.get("meta", {}))


def _src_to_cache(s: S.Source) -> dict:
    return {"kind": s.kind, "cues": s.cues, "meta": s.meta}


def collect(url: str, slug: str | None, audio: Path | None, use_cache: bool = True) -> tuple[list[S.Source], dict]:
    """Every witness we can reach, plus notes on what wasn't reachable."""
    vid = video_id(url)
    ev = _load_evidence(vid) if use_cache else {}
    report = {"videoId": vid, "sources": [], "missing": []}
    out: list[S.Source] = []

    # captions
    if "captions" in ev:
        if ev["captions"]:
            out.append(_src_from_cache(ev["captions"]["name"], ev["captions"]))
    else:
        cap = S.captions(url)
        ev["captions"] = ({"name": cap.name, **_src_to_cache(cap)} if cap else None)
        if cap:
            out.append(cap)
    if not any(s.kind == "captions" for s in out):
        report["missing"].append("captions")

    # this song's verified words (arrangement may differ - that is fine, alignment handles it)
    lib = S.library(slug) if slug else None
    if lib:
        out.append(lib)
    else:
        report["missing"].append("library")

    # listens
    asr_names = ("asr_large", "asr_turbo", "asr_prompted")
    cached = [n for n in asr_names if n in ev.get("asr", {})]
    if cached:
        for n in cached:
            out.append(_src_from_cache(n, ev["asr"][n]))
    elif audio and Path(audio).exists():
        ctx = ""
        if lib:
            ctx = (lib.meta.get("title", "") + ". " + " ".join(c["text"] for c in lib.cues))[:700]
        elif any(s.kind == "captions" for s in out):
            ctx = next(s for s in out if s.kind == "captions").text[:700]
        t = time.time()
        passes = S.asr_passes(Path(audio), ctx)
        ev["asr"] = {p.name: _src_to_cache(p) for p in passes}
        report["asr_seconds"] = round(time.time() - t, 1)
        out.extend(passes)
    if not any(s.kind == "asr" for s in out):
        report["missing"].append("audio")

    if use_cache:
        _save_evidence(vid, ev)
    report["sources"] = [s.name for s in out]
    return out, report


def analyze(url: str, slug: str | None = None, audio: Path | None = None, use_cache: bool = True) -> dict:
    vid = video_id(url)
    t_start = time.time()

    # 0) a human already confirmed this exact recording -> instant, final
    ver = S.verified_recording(vid, REPO)
    if ver and ver.get("lyrics"):
        return {"verdict": "verified", "lyrics": ver["lyrics"], "lines": ver.get("lines", []),
                "checks": [], "report": {"videoId": vid, "sources": ["verified_recording"],
                                         "note": "human-verified for this exact recording"}}

    srcs, report = collect(url, slug, audio, use_cache)
    asr = [s for s in srcs if s.kind == "asr"]
    weights = {s.name: s.weight for s in srcs}

    # 1) the spine: the best listen's timed lines
    lib = next((s for s in srcs if s.kind == "library"), None)
    if asr:
        primary = max(asr, key=lambda s: s.weight)
        words = [w for c in primary.cues for w in (c.get("words") or [])]
        if lib and words:
            # segment the performance into the song's known lines (repeats allowed)
            spine = align.segment_by_library(words, lib)
            for ln in spine:   # carry the listen's own confidence onto each line
                cs = [c for c in primary.cues if c["t0"] <= ln["t0"] <= c["t1"] + 0.01]
                ln["conf"] = cs[0]["conf"] if cs else 0.6
        else:
            # blind: pause/punctuation lines. (Re-cutting by the song's own repeats was
            # measured and made line breaks worse; the words were already right.)
            spine = align.build_spine(primary)
        spine_src = primary.name
    else:
        cap = next((s for s in srcs if s.kind == "captions"), None)
        if cap:
            spine = [{"t0": c["t0"], "t1": c["t1"], "text": tidy_display(c["text"]), "words": [], "conf": c["conf"]}
                     for c in cap.cues]
            spine_src = cap.name
        else:
            return {"verdict": "unverified", "lyrics": [], "lines": [], "checks": [],
                    "report": {**report, "note": "no recording evidence: needs audio or captions"}}

    # 2) every witness projected onto the spine
    projections = {}
    for s in srcs:
        if s.name == spine_src:
            projections[s.name] = [{"text": l["text"], "cue": i, "conf": l["conf"], "coverage": 1.0}
                                   for i, l in enumerate(spine)]
        elif s.kind == "library" and spine and "lib" in spine[0]:
            projections[s.name] = align.library_projection(spine, s)
        else:
            projections[s.name] = align.project(spine, s)

    # 3) decide, then let repeats vote
    lines = consensus.decide(spine, projections, weights, lib.cues if lib else None)
    lines = consensus.vote_repeats(lines)

    # 4) drop what is not congregation lyric: likely speech / noise
    kept = []
    for ln in lines:
        speech = (len(ln["sources"]) <= 1 and ln["status"] == "unverified"
                  and "library" not in ln["sources"] and _looks_spoken(ln["text"]))
        # a 1-2 word scrap nobody else corroborates (a trailing "You", a breath
        # heard as a word) is noise, not a congregation line
        scrap = ("library" not in ln["sources"] and len(key(ln["text"]).split()) <= 2
                 and not any(k.startswith("captions") for k in ln["sources"]))
        if ln["status"] == "excluded":
            report.setdefault("excluded", []).append({"t0": ln["t0"], "text": ln["text"]})
            continue
        if speech or scrap:
            ln["status"] = "excluded"; ln["why"] += "; looks spoken, not sung"
            report.setdefault("excluded", []).append({"t0": ln["t0"], "text": ln["text"]})
            continue
        kept.append(ln)
    lines = kept

    # 5) structure
    blks = structure.label(structure.blocks(lines))
    lyrics = [{"label": b["label"], "lines": [l["text"] for l in b["lines"]]} for b in blks if b["lines"]]

    checks = [{"t0": max(0, (l["t0"] or 0) - 2), "t1": l["t1"], "text": l["text"],
               "options": [l["text"]] + [a["text"] for a in l["alts"] if key(a["text"]) != key(l["text"])],
               "why": l["why"]} for l in lines if l["status"] == "check"]
    n_ver = sum(1 for l in lines if l["status"] == "verified")
    if not lines:
        verdict = "unverified"
    elif checks and len(checks) <= max(3, len(lines) // 4):
        verdict = "check"
    elif checks:
        verdict = "unverified"
    elif n_ver >= 0.9 * len(lines):
        verdict = "verified"
    else:
        verdict = "unverified"

    report.update({"lines": len(lines), "verified": n_ver, "checks": len(checks),
                   "seconds": round(time.time() - t_start, 1),
                   "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    return {"verdict": verdict, "lyrics": lyrics, "lines": lines, "checks": checks, "report": report}


def _looks_spoken(text: str) -> bool:
    t = text.lower()
    return bool(re.search(r"\b(thank you|let's|lets|everybody|come on|sing it|one more time|amen|hey|alright|all right|okay)\b", t)) \
        or len(t.split()) > 16


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("url"); ap.add_argument("--slug"); ap.add_argument("--audio"); ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    r = analyze(a.url, a.slug, Path(a.audio) if a.audio else None, use_cache=not a.no_cache)
    print(json.dumps({k: r[k] for k in ("verdict", "report")}, indent=1))
    for b in r["lyrics"]:
        print(f"\n[{b['label']}]")
        for l in b["lines"]:
            print("  " + l)
