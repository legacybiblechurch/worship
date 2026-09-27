"""Regression / accuracy harness.

For every song that has a video and cached evidence (or audio on disk), run the
engine and score it against the human-verified library words:

    wer        word error rate of the engine's full text vs the library text
    line_hit   share of library lines the engine reproduced (>= 0.9 similar)
    extra      lines the engine produced that match no library line
    checks     how many lines it flagged for a human

Ground truth for a RECORDING lives in verified/<videoId>.json; until a song
has one, its library words are the reference (arrangement differences count
against us, which is the honest direction to be wrong in).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "prep"))
import engine  # noqa: E402
import lib_songs  # noqa: E402
from norm import sim, wer  # noqa: E402


def score(result: dict, ref_lyrics: list[dict]) -> dict:
    ref_lines = [l for b in ref_lyrics for l in b["lines"]]
    out_lines = [l for b in result["lyrics"] for l in b["lines"]]
    hit = sum(1 for r in ref_lines if any(sim(r, o) >= 0.9 for o in out_lines))
    extra = sum(1 for o in out_lines if not any(sim(o, r) >= 0.9 for r in ref_lines))
    # word accuracy independent of arrangement: each engine line against the
    # library line it most resembles (a chorus sung 6x is scored 6x, not
    # penalised for existing). Lines matching nothing count as fully wrong.
    errs, n = 0.0, 0
    for o in out_lines:
        best = max(ref_lines, key=lambda r: sim(o, r)) if ref_lines else ""
        w = len(o.split())
        errs += (wer(best, o) if sim(o, best) >= 0.5 else 1.0) * w
        n += w
    return {
        "line_wer": round(errs / max(1, n), 3),
        "wer": round(wer(" ".join(ref_lines), " ".join(out_lines)), 3),
        "line_hit": round(hit / max(1, len(ref_lines)), 3),
        "extra": extra, "lines_out": len(out_lines), "lines_ref": len(ref_lines),
        "checks": len(result["checks"]), "verdict": result["verdict"],
    }


def main(audio_dir: Path, slugs: list[str] | None, use_library: bool = True) -> None:
    songs = lib_songs.load_songs()
    rows = []
    for slug, song in songs.items():
        if slugs and slug not in slugs:
            continue
        vid = engine.video_id(song.get("youtube", ""))
        if not vid:
            continue
        audio = next(iter(audio_dir.glob(vid + ".*")), None)
        have_ev = engine._evidence_path(vid).exists()
        if not audio and not have_ev:
            continue
        r = engine.analyze(song["youtube"], slug if use_library else None, audio)
        sc = score(r, song["lyrics"])
        sc.update(slug=slug, sources=r["report"].get("sources", []))
        rows.append(sc)
        print(f'{slug:42s} lineWER={sc["line_wer"]:.3f} textWER={sc["wer"]:.3f} hit={sc["line_hit"]:.2f} extra={sc["extra"]:2d} checks={sc["checks"]:2d} {sc["verdict"]}')
    if rows:
        avg = lambda k: sum(r[k] for r in rows) / len(rows)  # noqa: E731
        print(f'\n{len(rows)} songs   mean lineWER {avg("line_wer"):.3f}   mean textWER {avg("wer"):.3f}   '
              f'mean line hit {avg("line_hit"):.3f}   mean extra {avg("extra"):.1f}   mean checks {avg("checks"):.1f}')
        (HERE.parent.parent / "tests").mkdir(exist_ok=True)
        (HERE.parent.parent / "tests" / "engine_report.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=str(HERE.parent.parent / "audio"))
    ap.add_argument("--slugs", nargs="*")
    ap.add_argument("--no-library", action="store_true", help="score the engine WITHOUT the song's library words (captions + listens only)")
    a = ap.parse_args()
    main(Path(a.audio), a.slugs, use_library=not a.no_library)
