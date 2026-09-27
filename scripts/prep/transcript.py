"""
Get the words that are actually sung in a YouTube video, in performance order.

Strategy, best to worst:
  1. Supadata transcript API  (SUPADATA_API_KEY)  -> source="subs"/"asr"
     Needed because YouTube hard-blocks yt-dlp from datacenter IPs (GitHub Actions)
     with "Sign in to confirm you're not a bot". Supadata runs its own infra.
  2. yt-dlp captions           -> source="subs"/"asr"   (works from residential IPs)
  3. Whisper on downloaded audio via Groq  -> source="whisper"
     (only when allow_audio=True and GROQ_API_KEY is set)
  4. Lyrics pasted in the video description  -> source="description"
     Last resort: words only, NO timing and NO performance structure. The reconcile
     step treats this as a reference and caps confidence low.

Returns: { "source", "is_asr", "cues": [{"t": float_seconds, "text": str}], "text": str }
or None if nothing could be obtained.

We keep the *cues* (timestamped lines) rather than collapsing to prose, so the reconcile
step can see genuine repeats / vamps instead of having them deduped away.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=240, **kw)


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


# ---------------------------------------------------------------- caption parsing


def _parse_json3(raw: str) -> list[dict]:
    data = json.loads(raw)
    cues = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        text = re.sub(r"\s+", " ", text)
        if text and text != "\n":
            cues.append({"t": round(ev.get("tStartMs", 0) / 1000, 2), "text": text})
    return cues


def _parse_vtt(raw: str) -> list[dict]:
    cues, cur_t, buf = [], None, []

    def flush():
        nonlocal buf, cur_t
        if cur_t is not None and buf:
            txt = re.sub(r"<[^>]+>", "", " ".join(buf))
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                cues.append({"t": cur_t, "text": txt})
        buf = []

    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s*-->", line)
        if m:
            flush()
            h, mn, s, ms = (int(x) for x in m.groups())
            cur_t = h * 3600 + mn * 60 + s + ms / 1000
        elif not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or re.fullmatch(r"\d+", line):
            continue
        else:
            buf.append(line)
    flush()

    # drop consecutive exact-duplicate cues (rolling-caption artifact) but keep
    # a line that genuinely recurs later after something else in between
    out = []
    for c in cues:
        if out and c["text"] == out[-1]["text"]:
            continue
        out.append(c)
    return out


def _cues_to_text(cues: list[dict]) -> str:
    return "\n".join(c["text"] for c in cues)


# ---------------------------------------------------------------- Supadata API


def _looks_manual(text: str) -> bool:
    """Heuristic: real caption tracks have sentence case + punctuation;
    auto-captions are lowercase runs with none."""
    sample = text[:600]
    return bool(re.search(r"[.,!?]", sample)) and sample != sample.lower()


_SUPADATA_BLOCKED = [""]   # set to the reason once the plan limit is hit this run


def _supadata_captions(url: str) -> dict | None:
    key = os.environ.get("SUPADATA_API_KEY")
    if not key:
        return None
    global LAST_ERROR
    if _SUPADATA_BLOCKED[0]:
        LAST_ERROR = _SUPADATA_BLOCKED[0]
        return None
    try:
        from http_util import request_json
        from urllib.parse import quote
        res = request_json(
            "GET",
            "https://api.supadata.ai/v1/transcript?lang=en&url=" + quote(url, safe=""),
            headers={"x-api-key": key},
            timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "429" in msg or "limit-exceeded" in msg:
            # the plan's monthly allowance is gone: every further call this run
            # would fail the same way, so stop asking (and stop burning time)
            _SUPADATA_BLOCKED[0] = "supadata: monthly plan limit reached - captions unavailable until it resets or the plan is upgraded"
            LAST_ERROR = _SUPADATA_BLOCKED[0]
        else:
            LAST_ERROR = f"supadata: {msg[:160]}"
        return None

    segs = res.get("content") or []
    cues = [{"t": round((s.get("offset", 0) or 0) / 1000, 2), "text": s.get("text", "").strip()}
            for s in segs if s.get("text", "").strip()]
    if len(cues) < 3:
        LAST_ERROR = "supadata: no captions on this video"
        return None
    full = _cues_to_text(cues)
    manual = _looks_manual(full)
    return {"source": "subs" if manual else "asr", "is_asr": not manual,
            "cues": cues, "text": full}


# ---------------------------------------------------------------- yt-dlp captions

# YouTube gates different player clients differently, and the gating changes often
# (and is harsher from datacenter IPs like GitHub Actions). Try several, in order.
_CLIENT_ARGS = [
    "youtube:player_client=default",
    "youtube:player_client=tv",
    "youtube:player_client=web_safari,mweb",
    "youtube:player_client=android,web",
    "youtube:player_client=ios",
]

LAST_ERROR = ""     # last yt-dlp failure reason, for surfacing in the draft notes
_YTDLP_BLOCKED = [False]  # once YouTube bot-blocks us this run, stop retrying yt-dlp


def _load_cues(path: Path) -> list[dict]:
    raw = path.read_text(errors="ignore")
    return _parse_json3(raw) if path.suffix == ".json3" else _parse_vtt(raw)


def _pick_track_urls(info: dict) -> list[tuple[str, bool]]:
    """(url, is_asr) for the best English json3 track from the info json, manual first."""
    out = []
    for key, is_asr in (("subtitles", False), ("automatic_captions", True)):
        tracks = info.get(key) or {}
        for lang in ("en", "en-US", "en-GB", "en-orig"):
            for t in tracks.get(lang, []):
                if t.get("ext") in ("json3", "srv3", "vtt") and t.get("url"):
                    out.append((t["url"], is_asr))
    # de-dup, keep order
    seen, uniq = set(), []
    for u, a in out:
        if u not in seen:
            seen.add(u)
            uniq.append((u, a))
    return uniq


def _fetch_track(url: str) -> list[dict]:
    """Download a timedtext track URL directly (separate code path from yt-dlp's own
    subtitle downloader, which is more aggressively rate-limited)."""
    if "fmt=" not in url:
        url += "&fmt=json3"
    try:
        from http_util import request_json
        data = request_json("GET", url, timeout=30)
        return _parse_json3(json.dumps(data))
    except Exception:
        try:
            import urllib.request as _u
            raw = _u.urlopen(_u.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "replace")
            return _parse_json3(raw) if raw.lstrip().startswith("{") else _parse_vtt(raw)
        except Exception:
            return []


def _ytdlp_captions(url: str) -> dict | None:
    global LAST_ERROR
    if not _have("yt-dlp"):
        LAST_ERROR = "yt-dlp not installed"
        return None
    if _YTDLP_BLOCKED[0]:
        LAST_ERROR = "yt-dlp blocked by YouTube this run"
        return None

    for client in _CLIENT_ARGS:
        with tempfile.TemporaryDirectory() as tmp:
            r = _run([
                "yt-dlp", "--skip-download",
                "--write-subs", "--write-auto-subs",
                "--sub-langs", "en.*,en",
                "--sub-format", "json3/vtt/best",
                "--write-info-json",
                "--extractor-args", client,
                "--no-warnings", "--no-progress",
                "-o", f"{tmp}/v.%(ext)s", url,
            ])
            d = Path(tmp)
            info_f = next(d.glob("*.info.json"), None)
            if not info_f:
                err = (r.stderr or r.stdout or "").strip()
                LAST_ERROR = err.splitlines()[-1][:200] if err else "no info json"
                if "not a bot" in err or "Sign in to confirm" in err:
                    _YTDLP_BLOCKED[0] = True
                    return None
                continue
            info = json.loads(info_f.read_text())
            manual_langs = set((info.get("subtitles") or {}).keys())

            # (a) files yt-dlp already wrote
            subs = [f for f in d.iterdir() if f.suffix in (".json3", ".vtt")]
            def is_manual(f: Path) -> bool:
                parts = f.name.split(".")
                return len(parts) > 2 and parts[1] in manual_langs

            for group, is_asr in ((sorted((f for f in subs if is_manual(f)), key=lambda p: p.suffix != ".json3"), False),
                                  (sorted((f for f in subs if not is_manual(f)), key=lambda p: p.suffix != ".json3"), True)):
                for f in group:
                    cues = _load_cues(f)
                    if len(cues) >= 3:
                        return {"source": "asr" if is_asr else "subs", "is_asr": is_asr,
                                "cues": cues, "text": _cues_to_text(cues)}

            # (b) direct track URLs from the info json
            for turl, is_asr in _pick_track_urls(info):
                cues = _fetch_track(turl)
                if len(cues) >= 3:
                    return {"source": "asr" if is_asr else "subs", "is_asr": is_asr,
                            "cues": cues, "text": _cues_to_text(cues)}

            LAST_ERROR = "info ok but no usable caption track"
    return None


# ---------------------------------------------------------------- whisper via Groq


def _download_audio(url: str, dest_dir: str) -> Path | None:
    """Grab the smallest usable audio-only stream. No ffmpeg needed - Groq's Whisper
    accepts m4a/webm/opus directly, so we don't re-encode."""
    if not _have("yt-dlp") or _YTDLP_BLOCKED[0]:
        return None
    out = f"{dest_dir}/audio.%(ext)s"
    fmt = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/worstaudio"
    for client in _CLIENT_ARGS:
        if _have("ffmpeg"):
            _run(["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "5",
                  "--extractor-args", client, "--no-warnings", "--no-progress", "-o", out, url])
        else:
            _run(["yt-dlp", "-f", fmt, "--extractor-args", client,
                  "--no-warnings", "--no-progress", "-o", out, url])
        files = [p for p in Path(dest_dir).glob("audio.*") if p.stat().st_size > 1000]
        if files:
            return files[0]
    return None


GROQ_WHISPER_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")


def _groq_whisper(audio: Path) -> dict | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    fields = {"model": GROQ_WHISPER_MODEL, "response_format": "verbose_json",
              "temperature": "0"}

    res = None
    try:
        import requests  # type: ignore
        with audio.open("rb") as fh:
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"},
                              data=fields, files={"file": (audio.name, fh, "audio/mpeg")},
                              timeout=600)
        r.raise_for_status()
        res = r.json()
    except Exception:
        # curl fallback (old-TLS dev machines / no requests)
        cmd = ["curl", "-sS", "--max-time", "600", url,
               "-H", f"Authorization: Bearer {key}"]
        for k, v in fields.items():
            cmd += ["-F", f"{k}={v}"]
        cmd += ["-F", f"file=@{audio}"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=660).stdout
        try:
            res = json.loads(out)
        except json.JSONDecodeError:
            return None
    if not res:
        return None

    segs = res.get("segments") or []
    cues = [{"t": round(s.get("start", 0), 2), "text": s.get("text", "").strip()}
            for s in segs if s.get("text", "").strip()]
    if not cues and res.get("text"):
        cues = [{"t": 0.0, "text": res["text"].strip()}]
    if not cues:
        return None
    return {"source": "whisper", "is_asr": True, "cues": cues, "text": _cues_to_text(cues)}


# ---------------------------------------------------------------- public


# ---------------------------------------------------------------- description lyrics

_NOISE_RE = re.compile(
    r"^\s*(?:$|#|https?://|www\.|lyrics?\s*[:\-]|verse\s*\d|chorus|bridge|"
    r"\*?music\s+(?:is\s+)?licen|ccli|writer[s]?\s*[:\-]|composer|performer|"
    r"artist[s]?\s*[:\-]|©|\(c\)|copyright|all rights|follow us|subscribe|"
    r"instagram|facebook|spotify|apple music|from the album|out now)",
    re.I,
)


def _description_lyrics(url: str) -> dict | None:
    vid = re.search(r"[A-Za-z0-9_-]{11}", url)
    if not vid:
        return None
    try:
        import urllib.request as _u
        html = _u.urlopen(
            _u.Request(f"https://www.youtube.com/watch?v={vid.group(0)}",
                       headers={"User-Agent": "Mozilla/5.0"}), timeout=20
        ).read().decode("utf-8", "replace")
    except Exception:
        return None
    m = re.search(r'"shortDescription":"(.*?)","', html, re.S)
    if not m:
        return None
    try:                       # the captured text is a JSON string body
        desc = json.loads('"' + m.group(1) + '"')
    except Exception:
        desc = m.group(1).replace("\\n", "\n").replace('\\"', '"')

    raw = [ln.strip() for ln in desc.split("\n")]

    _END_RE = re.compile(r"^\s*(writer|composer|performer|artist|album|©|\(c\)|"
                         r"copyright|all rights|ccli|follow|subscribe)\b", re.I)
    _LYRIC_MARK = re.compile(r"^\s*lyrics?\s*[:\-]?\s*$", re.I)

    # if there's a "Lyrics:" heading, take from there until an end marker
    region = None
    for i, ln in enumerate(raw):
        if _LYRIC_MARK.match(ln):
            region = raw[i + 1:]
            break
    if region is not None:
        out = []
        blanks = 0
        for ln in region:
            if _END_RE.match(ln):
                break
            if not ln:
                blanks += 1
                if blanks >= 2 and out:
                    break
                continue
            blanks = 0
            if not _NOISE_RE.match(ln) and len(ln) <= 90:
                out.append(ln)
        lyric = out
    else:
        # no heading: keep the longest run, tolerating single blank lines
        best, cur, gap = [], [], 0
        for ln in raw + ["", ""]:
            keep = ln and not _NOISE_RE.match(ln) and len(ln) <= 90 and len(ln.split()) <= 14
            if keep:
                cur.append(ln)
                gap = 0
            elif not ln and gap == 0 and cur:
                gap = 1  # allow one blank between verses
            else:
                if len(cur) > len(best):
                    best = cur
                cur, gap = [], 0
        lyric = best

    if len(lyric) < 6:
        return None
    cues = [{"t": 0.0, "text": ln} for ln in lyric]
    return {"source": "description", "is_asr": True, "cues": cues,
            "text": "\n".join(lyric)}


def _whisper_from_url(url: str) -> dict | None:
    with tempfile.TemporaryDirectory() as tmp:
        audio = _download_audio(url, tmp)
        if not audio:
            return None
        try:
            return _groq_whisper(audio)
        except Exception:
            return None


def fetch_transcript(url: str, *, allow_audio: bool = False,
                     force_audio: bool = False) -> dict | None:
    """
    allow_audio  - fall back to Whisper only if no captions exist
    force_audio  - go straight to Whisper (used to re-try a song whose auto-captions
                   were too garbled to reconcile)
    """
    if force_audio and allow_audio:
        got = _whisper_from_url(url)
        if got:
            return got

    global LAST_ERROR
    got = _supadata_captions(url)          # works from any IP
    if got:
        return got
    reasons = [LAST_ERROR] if LAST_ERROR else []

    for _ in range(2):                     # residential-IP path / local dev
        got = _ytdlp_captions(url)
        if got:
            return got
    if LAST_ERROR and LAST_ERROR not in reasons:
        reasons.append("yt-dlp: " + LAST_ERROR)

    if allow_audio:
        got = _whisper_from_url(url)
        if got:
            return got

    # every source failed: keep ALL the reasons, so the draft note says why
    # (a later step used to overwrite the first cause with the last one)
    LAST_ERROR = "; ".join(reasons) or "no captions"
    return _description_lyrics(url)         # words only, no structure


if __name__ == "__main__":
    import sys

    u = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=LULK2nZ6sCc"
    allow = "--audio" in sys.argv
    got = fetch_transcript(u, allow_audio=allow)
    if not got:
        print("no transcript")
    else:
        print(f'source={got["source"]} is_asr={got["is_asr"]} cues={len(got["cues"])}')
        print("\n".join(f'  {c["t"]:>7.1f}  {c["text"]}' for c in got["cues"][:40]))
