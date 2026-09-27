"""The listener. Runs every minute on the church Mac (launchd).

Why this exists: YouTube refuses audio downloads from GitHub's servers, so the
one step that must happen from a normal internet connection - fetching the
recording - runs here. Everything else (captions, the library, the consensus
engine) runs anywhere. This script:

  1. pulls the site repo
  2. finds drafts marked needsAudio (the Studio's "find" produced them)
  3. downloads the audio, runs the engine with all three listens
  4. writes the finished draft + evidence, commits, pushes

If the Mac is off, the Studio simply shows "waiting for the church computer".
Nothing here needs a person.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LBC = Path.home() / ".lbc"
AUDIO = LBC / "audio"
LOCK = LBC / "helper.lock"
sys.path.insert(0, str(REPO / "scripts" / "engine"))
sys.path.insert(0, str(REPO / "scripts" / "prep"))


def sh(*args, check=True, **kw):
    return subprocess.run(args, cwd=str(REPO), check=check, text=True, capture_output=True, **kw)


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def download(video_id: str) -> Path | None:
    AUDIO.mkdir(parents=True, exist_ok=True)
    for f in AUDIO.glob(video_id + ".*"):
        return f
    url = f"https://www.youtube.com/watch?v={video_id}"
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "--no-warnings",
                        "-f", "bestaudio[ext=m4a]/bestaudio", "-o", str(AUDIO / "%(id)s.%(ext)s"), url],
                       text=True, capture_output=True)
    if r.returncode != 0:
        log(f"download failed for {video_id}: {r.stderr.strip()[-200:]}")
        return None
    return next(iter(AUDIO.glob(video_id + ".*")), None)


def main() -> None:
    LBC.mkdir(exist_ok=True)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                                      # previous run still going
    for line in (LBC / "engine.env").read_text().splitlines() if (LBC / "engine.env").exists() else []:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

    sh("git", "pull", "-q", "--no-rebase", "--no-edit", "-X", "theirs", check=False)
    import engine  # noqa: E402  (after pull, so it is the current engine)

    todo = []
    for p in sorted((REPO / "drafts").glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        if d.get("needsAudio") and d.get("candidates"):
            todo.append((p, d))
    if not todo:
        return

    changed = []
    for p, d in todo:
        cands = [c for c in d["candidates"] if c.get("videoId")]
        if d.get("forced"):
            cands = [c for c in cands if c["videoId"] == d["forced"]] + [c for c in cands if c["videoId"] != d["forced"]]
        # listen to the top two candidates at most - that is what the person will choose between
        for c in cands[:2]:
            vid = c["videoId"]
            log(f"listening: {d.get('title')} / {vid}")
            audio = download(vid)
            if not audio:
                c["engine"] = {"verdict": "unverified", "report": {"note": "could not fetch the recording"}}
                continue
            slug = None if d.get("isNew") else d.get("slug")
            try:
                res = engine.analyze(c["url"], slug, audio)
            except Exception as e:  # noqa: BLE001
                log(f"engine failed on {vid}: {e}")
                c["engine"] = {"verdict": "unverified", "report": {"note": f"engine error: {str(e)[:120]}"}}
                continue
            c["engine"] = {k: res[k] for k in ("verdict", "lines", "checks", "report")}
            if res["lyrics"]:
                c["lyrics"] = res["lyrics"]
                c["transcriptSource"] = "engine"
                c["confidence"] = int(100 * (res["report"].get("verified", 0) / max(1, res["report"].get("lines", 1))))
                c["notes"] = {"verified": "Every line verified by independent listens.",
                              "check": f'{len(res["checks"])} line(s) need a quick check.',
                              "unverified": "The recording was hard to hear; check the words."}[res["verdict"]]
        d["needsAudio"] = False
        d["listenedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
        changed.append(d.get("title") or p.stem)

    sh("git", "add", "drafts", "evidence")
    if sh("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    sh("git", "-c", "user.name=lbc-listener", "-c", "user.email=listener@users.noreply.github.com",
       "commit", "-q", "-m", "engine: listened to " + ", ".join(changed) + " [skip ci]")
    for _ in range(4):
        if sh("git", "push", "-q", check=False).returncode == 0:
            log("pushed: " + ", ".join(changed)); return
        sh("git", "pull", "-q", "--no-rebase", "--no-edit", "-X", "ours", check=False)
    log("push failed after retries")


if __name__ == "__main__":
    main()
