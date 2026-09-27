"""
Worship prep pipeline.  Run with no args on a schedule; it does both passes:

  Pass A (draft)  - for every Sheet row not yet approved: find candidate videos and
                    draft lyrics for each. Writes drafts/<slug>.json + drafts/status.json.
                    Never touches js/songs-data.js.

  Pass B (apply)  - for every row with Review = "Approve": take the chosen video
                    (Sheet "Video" column, else the top candidate), apply any "Fixes",
                    write the final entry into js/songs-data.js and rebuild
                    js/worship-songs.js.

  python3 run.py draft     # only pass A
  python3 run.py apply     # only pass B
  python3 run.py           # both

Env: YOUTUBE_API_KEY, GEMINI_API_KEY (or ANTHROPIC_API_KEY), [GROQ_API_KEY]
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import align
import lib_songs
import reconcile as rec
import sheet as sheet_mod
import videos as yt
from resolve import resolve
from transcript import fetch_transcript

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "drafts"
STATUS = DRAFTS / "status.json"
APPROVALS = REPO / "drafts" / "approvals.json"   # slug -> {video, approvedAt}


def _load_approvals() -> dict:
    try:
        return json.loads(APPROVALS.read_text())
    except Exception:
        return {}


def _record_approval(slug: str, video_url: str) -> None:
    data = _load_approvals()
    vid = yt.video_id(video_url) or video_url
    if data.get(slug, {}).get("video") == vid:
        return
    data[slug] = {"video": vid, "approvedAt": dt.date.today().isoformat()}
    APPROVALS.write_text(json.dumps(data, indent=2, sort_keys=True))

MAX_CANDIDATES = 8        # search pool; we only fetch transcripts until RECONCILE_TOP hit
RECONCILE_TOP = 2         # draft lyrics for the first N candidates that have a transcript
ALLOW_AUDIO = bool(os.environ.get("GROQ_API_KEY"))


def next_sunday(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return (today + dt.timedelta(days=(6 - today.weekday()) % 7)).isoformat()


def _sig(candidate_ids: list[str], reference: list | None, fixes: str = "") -> str:
    # sorted + deduped so day-to-day YouTube search-order / view-count jitter on the
    # same set of videos does not trigger a needless re-draft; the Fixes text IS
    # included so editing it re-drafts the song
    h = hashlib.sha256()
    h.update("|".join(sorted(set(candidate_ids))).encode())
    h.update(json.dumps(reference or [], sort_keys=True).encode())
    h.update(fixes.strip().encode())
    return h.hexdigest()[:16]


def _draft_path(slug: str) -> Path:
    return DRAFTS / f"{slug}.json"


def _load_draft(slug: str) -> dict | None:
    p = _draft_path(slug)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- pass A


def draft_row(row: sheet_mod.Row, songs: dict) -> dict:
    slug, title, is_new = resolve(row.song)
    row.slug, row.title, row.is_new = slug, title, is_new
    reference = None if is_new else songs[slug]["lyrics"]

    forced = yt.video_id(row.video) if row.video else None

    # Already perfected in the library (real video + lyrics) and the person isn't
    # forcing a new video or asking for a redo -> don't spend search/transcript/LLM.
    # Just present the locked-in version; approving it is a no-op that keeps it.
    if not row.redo and not forced and not is_new:
        cur_vid = yt.video_id(songs[slug].get("youtube", ""))
        if cur_vid:
            approved_at = _load_approvals().get(slug, {}).get("approvedAt", "")
            prev = _load_draft(slug)
            if (prev and prev.get("signature") == "library"
                    and prev["candidates"] and prev["candidates"][0]["videoId"] == cur_vid
                    and prev.get("approvedAt", "") == approved_at):
                prev["input"] = row.song
                return prev
            done = {
                "slug": slug, "title": title, "input": row.song, "isNew": False,
                "forced": None, "signature": "library",
                "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "libraryReady": True,
                "approvedAt": approved_at,
                "candidates": [{
                    "videoId": cur_vid,
                    "url": f"https://www.youtube.com/watch?v={cur_vid}",
                    "title": title, "channel": "", "duration": "", "durationSec": 0,
                    "views": 0, "hasCaptions": True, "transcriptSource": "library",
                    "lyrics": songs[slug]["lyrics"], "confidence": 100,
                    "order": "", "notes": (
                        ("Prepared and approved " + approved_at + ". " if approved_at
                         else "Already in the library. ")
                        + "Nothing to review - set Review = Approve to add it to this "
                          "Sunday, or put 'redo' in Review to rebuild it from scratch."),
                }],
            }
            DRAFTS.mkdir(exist_ok=True)
            _draft_path(slug).write_text(json.dumps(done, indent=2, ensure_ascii=False))
            return done

    # candidate videos (wider net — the highest-view "official" upload often has no
    # captions, so we need enough options to find ones that do)
    prev = _load_draft(slug)
    title_key = title.strip().lower()

    # a YouTube search costs 100 quota units (10,000/day free = 100 searches) — with
    # the pipeline now running every few minutes, re-searching every cycle for a song
    # nobody has touched would burn that in under an hour. Reuse the last search's
    # results as long as the title text hasn't changed, it's not a "redo", and the
    # cache isn't stale (a lingering row still gets a fresh look periodically).
    cache_fresh = False
    if prev and prev.get("titleKey") == title_key and prev.get("searchCandidates"):
        try:
            age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(prev["generatedAt"])
            cache_fresh = age < dt.timedelta(hours=12)
        except Exception:
            cache_fresh = False

    candidates: list[dict] = []
    if forced:
        d = yt.details(forced)
        if d:
            candidates.append(d)
    search_pool = (prev["searchCandidates"] if (cache_fresh and not row.redo)
                   else yt.search(title, max_results=MAX_CANDIDATES))
    for c in search_pool:
        if c["videoId"] not in {x["videoId"] for x in candidates}:
            candidates.append(dict(c))

    signature = _sig([c["videoId"] for c in candidates], reference, row.fixes)
    if prev and prev.get("signature") == signature and not row.redo:
        prev["input"] = row.song
        prev["forced"] = forced
        return prev  # unchanged — skip re-reconcile

    for c in candidates:
        c.setdefault("lyrics", None)
        c["transcriptSource"] = "none"
        c["confidence"] = 0
        c["notes"] = ""
        c["order"] = ""

    # walk candidates in rank order, drafting until RECONCILE_TOP of them have lyrics
    import transcript as _t
    drafted = 0
    for c in candidates:
        if drafted >= RECONCILE_TOP and c["videoId"] != forced:
            break
        try:
            tr = fetch_transcript(c["url"], allow_audio=ALLOW_AUDIO)
            if not tr:
                c["notes"] = f"No transcript ({_t.LAST_ERROR or 'no captions'})."
                continue
            c["transcriptSource"] = tr["source"]
            r = rec.reconcile(title, reference, tr, fixes=row.fixes)
            if r["confidence"] < 55 and ALLOW_AUDIO and tr["source"] == "asr":
                tr2 = fetch_transcript(c["url"], allow_audio=True, force_audio=True)
                if tr2:
                    r2 = rec.reconcile(title, reference, tr2, fixes=row.fixes)
                    if r2["confidence"] > r["confidence"]:
                        tr, r = tr2, r2
                        c["transcriptSource"] = tr2["source"]
            # stamp each line with when it is sung, so the prep page can jump
            # the video to any line instead of making someone scrub for it
            c.update(lyrics=align.annotate(r["lyrics"], tr.get("cues") or []),
                     confidence=r["confidence"], notes=r["notes"], order=r["order"])
            drafted += 1
        except Exception as e:  # noqa: BLE001 — one bad video shouldn't kill the run
            c["notes"] = f"Draft failed: {e}"

    # make sure the person always has lyrics to review: fill any candidate that still
    # has none - the forced (pasted) one first, then the top pick - from the library
    # if we have it, else the model's best recollection of the song.
    def _fill(c):
        if c.get("lyrics"):
            return
        if reference:
            lyr, note, conf = reference, (
                "This video has no captions, so these are the lyrics already in the library, "
                "in the song's standard order. Play the video through and check the verses "
                "and repeats match - note any change in Fixes."), 55
            if row.fixes.strip():
                try:
                    r = rec.reconcile(title, reference, {"source": "reference", "cues": []},
                                      fixes=row.fixes)
                    lyr, note = r["lyrics"], "Library lyrics with your Fixes applied - " + \
                        "still no captions on this video, so double-check the order against it."
                except Exception:  # noqa: BLE001
                    pass
            c.update(lyrics=lyr, transcriptSource="reference", confidence=conf, order="", notes=note)
        else:
            try:
                r = rec.from_title(title, fixes=row.fixes)
                c.update(lyrics=r["lyrics"], transcriptSource="fromtitle",
                         confidence=r["confidence"], order=r["order"], notes=r["notes"])
            except Exception as e:  # noqa: BLE001
                c["notes"] = ("This video has no captions and the song isn't in the library "
                              "yet. Paste a lyric video that has captions, or type the lyrics "
                              "into the Fixes column. (" + str(e)[:80] + ")")

    forced_c = next((c for c in candidates if c["videoId"] == forced), None)
    if forced_c is not None:
        _fill(forced_c)
    if candidates and not any(c.get("lyrics") for c in candidates):
        _fill(candidates[0])

    # float the candidates we actually drafted lyrics for (best confidence) to the top,
    # keeping a forced pick first of all
    candidates.sort(key=lambda c: (
        c["videoId"] == forced,
        bool(c.get("lyrics")),
        c.get("confidence", 0),
    ), reverse=True)

    draft = {
        "slug": slug,
        "title": title,
        "input": row.song,
        "isNew": is_new,
        "forced": forced,
        "signature": signature,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "titleKey": title_key,
        "searchCandidates": search_pool,
        "candidates": candidates,
    }
    DRAFTS.mkdir(exist_ok=True)
    _draft_path(slug).write_text(json.dumps(draft, indent=2, ensure_ascii=False))
    return draft


# ---------------------------------------------------------------- pass B


def apply_row(row: sheet_mod.Row, songs: dict) -> tuple[str, str]:
    """Returns (slug, message). Writes into songs-data.js on success."""
    slug, title, is_new = resolve(row.song)
    forced = yt.video_id(row.video) if row.video else None

    # already applied? (song in library with the chosen video) -> idempotent no-op
    if not row.redo and slug in songs:
        cur_vid = yt.video_id(songs[slug].get("youtube", ""))
        if cur_vid and (cur_vid == forced or not forced):
            url = f"https://www.youtube.com/watch?v={cur_vid}"
            _record_approval(slug, url)
            return slug, f"approved — {url}"

    draft = _load_draft(slug)
    cands = (draft or {}).get("candidates", [])
    chosen = None
    if forced:
        # a pasted video URL is applied straight away, even with no draft yet -
        # one cycle instead of two
        chosen = next((c for c in cands if c["videoId"] == forced), None) or yt.details(forced)
    if not chosen and not draft:
        return slug, "approved but no draft yet — will apply next run"
    if not chosen:
        chosen = next((c for c in cands if c.get("lyrics")), None) or (cands[0] if cands else None)
    if not chosen:
        return slug, "approved but no usable video found"

    lyrics = chosen.get("lyrics")
    fixes = row.fixes.strip()
    if fixes or not lyrics:
        reference = None if is_new else (songs[slug]["lyrics"] if slug in songs else None)
        base = reference or lyrics            # what a fix should be applied to
        tr = fetch_transcript(chosen["url"], allow_audio=ALLOW_AUDIO)
        if tr:
            lyrics = rec.reconcile(title, reference, tr, fixes=row.fixes)["lyrics"]
        elif fixes and base:
            # no transcript, but there's a correction to apply to the base lyrics
            lyrics = rec.reconcile(title, base, {"source": "reference", "cues": []},
                                   fixes=row.fixes)["lyrics"]
        elif base:
            lyrics = base
        else:
            try:
                lyrics = rec.from_title(title, fixes=row.fixes)["lyrics"]
            except Exception:  # noqa: BLE001
                return slug, "approved but no captions and not in the library — add a lyric video or type the words in Fixes"

    # timestamps are per-recording scratch data for the review page - the library
    # entry outlives any one video, so it stores the words only
    lib_songs.upsert_song(slug, title=title, youtube=chosen["url"],
                          lyrics=align.strip_times(lyrics))
    _record_approval(slug, chosen["url"])
    return slug, f"approved — {chosen['url']}"


# ---------------------------------------------------------------- driver


def write_status(entries: list[dict], sunday: str) -> None:
    DRAFTS.mkdir(exist_ok=True)
    # skip the write entirely if nothing substantive changed, so idle scheduled
    # runs produce no commit
    if STATUS.exists():
        try:
            old = json.loads(STATUS.read_text())
            if old.get("sunday") == sunday and old.get("songs") == entries:
                return
        except Exception:
            pass
    STATUS.write_text(json.dumps({
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sunday": sunday,
        "songs": entries,
    }, indent=2, ensure_ascii=False))


def main(mode: str) -> None:
    rows = sheet_mod.load()
    songs = lib_songs.load_songs()
    sunday = next_sunday()
    do_draft = mode in ("draft", "both")
    do_apply = mode in ("apply", "both")

    status: list[dict] = []
    approved_slugs: list[str] = []

    for row in rows:
        entry = {"input": row.song, "review": row.review, "chosenVideo": row.video,
                 "status": "queued", "confidence": None, "message": ""}
        try:
            if do_apply and row.approved:
                slug, msg = apply_row(row, songs)
                entry.update(slug=slug, status="approved", message=msg)
                if "approved —" in msg:
                    approved_slugs.append(slug)
                else:
                    # not fully applied yet — still needs a draft
                    if do_draft:
                        d = draft_row(row, songs)
                        entry["confidence"] = _best_conf(d)
            elif do_draft:
                d = draft_row(row, songs)
                best = _best_conf(d)
                entry.update(slug=d["slug"], status="draft",
                             confidence=best,
                             message=f'{len(d["candidates"])} candidate(s)')
            status.append(entry)
        except Exception as e:  # noqa: BLE001
            entry.update(status="error", message=str(e))
            status.append(entry)
            traceback.print_exc()

    if do_apply:
        # the live setlist always mirrors the approved rows of the CURRENT sheet, in
        # sheet order - so swapping in next week's songs clears last week's until they
        # are approved (rather than leaving stale songs on Control/Display)
        ordered = []
        for row in rows:
            if row.approved:
                s, _, _ = resolve(row.song)
                if s in approved_slugs and s not in ordered:
                    ordered.append(s)
        cur = lib_songs.load_setlist()
        if ordered != cur:
            lib_songs.write_setlist(ordered, sunday=sunday)

    write_status(status, sunday)
    print(json.dumps(status, indent=2, ensure_ascii=False))


def _best_conf(draft: dict) -> int | None:
    confs = [c.get("confidence", 0) for c in draft.get("candidates", []) if c.get("lyrics")]
    return max(confs) if confs else None


def draft_one(name: str, video: str = "") -> None:
    """Draft a single song by name - the path Worship Studio's "Add a song" uses.

    No sheet, no setlist changes, no library writes: it only produces
    drafts/<slug>.json, which the Studio polls for and then shows the person
    (video + drafted words) to confirm. Any failure is written into that same
    file so the Studio can show a human-readable reason instead of waiting
    forever.
    """
    # "redo" = always search and transcribe afresh. A person pressing "find" in
    # the Studio wants a real attempt now, not last week's cached draft.
    row = sheet_mod.Row(song=name, video=video or "", review="redo")
    songs = lib_songs.load_songs()
    slug, title, _ = resolve(name)
    try:
        d = draft_row(row, songs)
        # The Exact Lyrics Engine decides the words, from evidence only. Here (on
        # GitHub's servers) it can use captions and the song's verified library
        # words; the recording itself gets listened to by the church Mac, which
        # picks up any draft still marked needsAudio.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
        import engine as eng
        known = None if d.get("isNew") else d["slug"]
        settled = False
        import tempfile
        import sources as esrc
        audio_dir = Path(tempfile.mkdtemp(prefix="lbc-audio-"))
        can_fetch = bool(os.environ.get("YT_PROXY"))
        listened = False
        for c in d["candidates"][:2]:
            audio = esrc.fetch_audio(c["videoId"], audio_dir) if can_fetch else None
            if can_fetch and not audio:
                c.setdefault("notes", "")
                c["fetchError"] = esrc.FETCH_ERROR
            listened = listened or bool(audio)
            try:
                res = eng.analyze(c["url"], known, audio)
            except Exception as e:  # noqa: BLE001
                c["engine"] = {"verdict": "unverified", "report": {"note": f"engine error: {str(e)[:120]}"}}
                continue
            c["engine"] = {k: res[k] for k in ("verdict", "lines", "checks", "report")}
            if res["lyrics"]:
                c["lyrics"] = res["lyrics"]; c["transcriptSource"] = "engine"
                c["confidence"] = int(100 * res["report"].get("verified", 0) / max(1, res["report"].get("lines", 1)))
            elif c.get("transcriptSource") == "fromtitle":
                # never present words the model merely remembered as if they were heard
                c["lyrics"] = None; c["confidence"] = 0; c["transcriptSource"] = "none"
                c["notes"] = "Waiting to listen to the recording."
            settled = settled or res["verdict"] == "verified"
        # audio was actually listened to here -> nothing left for a listener machine
        d["needsAudio"] = not settled and not listened
        if listened:
            d["listenedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        _draft_path(d["slug"]).write_text(json.dumps(d, indent=2, ensure_ascii=False))
        print(json.dumps({"slug": d["slug"], "candidates": len(d["candidates"]),
                          "needsAudio": d["needsAudio"]}))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        DRAFTS.mkdir(exist_ok=True)
        _draft_path(slug).write_text(json.dumps({
            "slug": slug, "title": title, "input": name, "isNew": slug not in songs,
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "error": str(e)[:200], "candidates": [],
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--song":
        draft_one(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    else:
        arg = sys.argv[1] if len(sys.argv) > 1 else "both"
        main({"draft": "draft", "apply": "apply", "both": "both"}.get(arg, "both"))
