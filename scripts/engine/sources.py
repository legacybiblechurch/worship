"""Evidence sources. Each returns a Source: a weighted list of timed cues.

A cue is {"t0": sec, "t1": sec, "text": str, "conf": 0..1}. Untimed sources
(the library) have t0 = t1 = None. Nothing here decides what the lyric is -
that is the consensus layer's job. These only collect what each witness says.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / "prep"
if str(PREP) not in sys.path:
    sys.path.insert(0, str(PREP))

# how much each witness is trusted before anything else is known about it
WEIGHTS = {
    "verified_recording": 1.00,   # a human confirmed these exact words for this exact video
    "captions_manual":    0.80,
    "library":            0.70,   # human-verified words for this SONG (arrangement may differ)
    "asr_large":          0.62,
    "asr_prompted":       0.30,   # biased toward the prompt; corroborates, never decides
    "asr_turbo":          0.52,
    "captions_auto":      0.45,
}


@dataclass
class Source:
    name: str
    kind: str                    # asr | captions | library | verified
    weight: float
    cues: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(c["text"] for c in self.cues)


# ───────────────────────────────────────────── captions

def captions(url: str) -> Source | None:
    try:
        import transcript as t
        got = t._supadata_captions(url)
    except Exception:  # noqa: BLE001
        got = None
    if not got:
        return None
    manual = got.get("source") == "subs"
    name = "captions_manual" if manual else "captions_auto"
    cues = []
    for c in got.get("cues", []):
        txt = (c.get("text") or "").strip()
        if txt and not txt.startswith("["):
            cues.append({"t0": float(c.get("t", 0)), "t1": None, "text": txt, "conf": 0.9 if manual else 0.6})
    # fill t1 from the next cue's start
    for i in range(len(cues) - 1):
        cues[i]["t1"] = cues[i + 1]["t0"]
    if cues:
        cues[-1]["t1"] = cues[-1]["t0"] + 4.0
    return Source(name, "captions", WEIGHTS[name], cues, {"manual": manual})


# ───────────────────────────────────────────── library / verified

def library(slug: str) -> Source | None:
    try:
        import lib_songs
        song = lib_songs.load_songs().get(slug)
    except Exception:  # noqa: BLE001
        song = None
    if not song or not song.get("lyrics"):
        return None
    cues = []
    for bi, b in enumerate(song["lyrics"]):
        for li, line in enumerate(b.get("lines", [])):
            cues.append({"t0": None, "t1": None, "text": line, "conf": 0.95,
                         "block": bi, "label": b.get("label", ""), "line": li})
    return Source("library", "library", WEIGHTS["library"], cues,
                  {"title": song.get("title"), "blocks": [b.get("label", "") for b in song["lyrics"]]})


def verified_recording(video_id: str, repo_root: Path) -> dict | None:
    p = repo_root / "verified" / f"{video_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return None
    return None


# ───────────────────────────────────────────── audio

FETCH_ERROR = ""


def fetch_audio(video_id: str, dest_dir: Path) -> Path | None:
    """Download the recording's audio with yt-dlp. YouTube refuses datacenter
    addresses (GitHub's runners), so on GitHub this goes through the residential
    proxy in YT_PROXY; from a home connection no proxy is needed."""
    global FETCH_ERROR
    import subprocess
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    for f in dest_dir.glob(video_id + ".*"):
        return f
    cmd = [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings",
           "-f", "bestaudio[abr<=128][ext=m4a]/bestaudio[ext=m4a]/bestaudio",
           "-o", str(dest_dir / "%(id)s.%(ext)s")]
    proxy = os.environ.get("YT_PROXY", "").strip()
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        FETCH_ERROR = (r.stderr.strip().splitlines() or ["download failed"])[-1][:200]
        return None
    return next(iter(dest_dir.glob(video_id + ".*")), None)


# ───────────────────────────────────────────── ASR (Groq Whisper)

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _groq_key() -> str:
    k = os.environ.get("GROQ_API_KEY", "")
    if not k:
        env = Path.home() / ".lbc" / "engine.env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("GROQ_API_KEY="):
                    k = line.split("=", 1)[1].strip()
    return k


def _whisper(audio: Path, model: str, prompt: str = "", tries: int = 3) -> dict | None:
    key = _groq_key()
    if not key:
        return None
    data = {"model": model, "response_format": "verbose_json", "language": "en", "temperature": "0"}
    if prompt:
        data["prompt"] = prompt[:900]
    for attempt in range(tries):
        try:
            with open(audio, "rb") as f:
                r = requests.post(GROQ_URL, headers={"Authorization": "Bearer " + key},
                                  data=list(data.items()) + [("timestamp_granularities[]", "word"),
                                                            ("timestamp_granularities[]", "segment")],
                                  files={"file": (audio.name, f)}, timeout=180)
            if r.status_code == 429:
                time.sleep(8 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                return None
            time.sleep(3)
    return None


def _asr_source(name: str, res: dict) -> Source:
    """Whisper JSON -> word-timed cues (one cue per segment, words kept)."""
    cues = []
    words = res.get("words") or []
    wi = 0
    for s in res.get("segments") or []:
        t0, t1 = float(s["start"]), float(s["end"])
        lp = float(s.get("avg_logprob", -0.5))
        nsp = float(s.get("no_speech_prob", 0.0))
        comp = float(s.get("compression_ratio", 1.0))
        # confidence: logprob near 0 is good; very repetitive (comp > 2.2) or
        # likely-silence segments are suspicious
        conf = max(0.05, min(1.0, 1.0 + lp))
        if comp > 2.2:
            conf *= 0.4
        if nsp > 0.6:
            conf *= 0.4
        seg_words = []
        while wi < len(words) and float(words[wi]["start"]) < t1 - 0.01:
            w = words[wi]
            if float(w["end"]) >= t0 - 0.01:
                seg_words.append({"w": w["word"], "t0": float(w["start"]), "t1": float(w["end"])})
            wi += 1
        txt = (s.get("text") or "").strip()
        if txt:
            cues.append({"t0": t0, "t1": t1, "text": txt, "conf": round(conf, 3),
                         "words": seg_words, "nsp": nsp, "lp": lp})
    return Source(name, "asr", WEIGHTS[name], cues, {"duration": res.get("duration")})


def asr_passes(audio: Path, context: str = "") -> list[Source]:
    """Three strategically different listens. Independent decoders (large-v3 and
    turbo) disagree in different places; the prompted pass biases toward known
    vocabulary (song title, previously verified words) without inventing lines."""
    out = []
    a = _whisper(audio, "whisper-large-v3")
    if a:
        out.append(_asr_source("asr_large", a))
    b = _whisper(audio, "whisper-large-v3-turbo")
    if b:
        out.append(_asr_source("asr_turbo", b))
    if context:
        c = _whisper(audio, "whisper-large-v3", prompt=context)
        if c:
            src = _asr_source("asr_prompted", c)
            # Whisper sometimes echoes the start of the prompt as if it were sung
            head = " ".join(context.split()[:4]).lower()
            if src.cues and head and src.cues[0]["text"].lower().startswith(head[: max(8, len(head) - 2)]):
                src.cues[0]["text"] = src.cues[0]["text"][len(head):].strip(" .,")
                src.cues[0]["words"] = src.cues[0]["words"][len(head.split()):]
            out.append(src)
    return out
