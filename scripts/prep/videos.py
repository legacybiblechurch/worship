"""
Find candidate YouTube videos for a song.

Two backends, picked automatically:
  * YouTube Data API v3   - used when YOUTUBE_API_KEY is set (official, stable)
  * yt-dlp "ytsearch"      - no key needed; reuses the yt-dlp we already depend on

Either way returns candidate dicts, best-first:
  { videoId, url, title, channel, publishedAt, durationSec, duration, views, hasCaptions }
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/youtube/v3"
_EXTRACTOR_ARGS = "youtube:player_client=default,tv,web_safari"
_VID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def video_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _VID_RE.search(s)
    return m.group(1) if m else None


def _mmss(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def _rank(cands: list[dict], limit: int) -> list[dict]:
    def score(c: dict) -> float:
        s = 0.0
        if c.get("hasCaptions"):
            s += 1000
        if 90 <= c.get("durationSec", 0) <= 540:      # a plausible single-song length
            s += 200
        s += min(c.get("views", 0) / 1e6, 50)
        return s

    return sorted(cands, key=score, reverse=True)[:limit]


# ---------------------------------------------------------------- Data API backend


def _api_get(path: str, **params) -> dict:
    params["key"] = os.environ["YOUTUBE_API_KEY"]
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "lbc-worship-prep"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _iso8601_to_seconds(dur: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mn, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mn * 60 + s


_QUERIES = ("{t} lyrics", "{t} lyric video", "{t} worship lyrics", "{t} hymn lyrics", "{t}")


def _search_api(title: str, max_results: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in (s.format(t=title) for s in _QUERIES):
        try:
            res = _api_get("search", part="snippet", q=q, type="video",
                           maxResults=max_results, videoEmbeddable="true")
        except Exception:
            continue
        for item in res.get("items", []):
            vid = item["id"]["videoId"]
            sn = item["snippet"]
            seen.setdefault(vid, {
                "videoId": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                "title": sn["title"], "channel": sn["channelTitle"],
                "publishedAt": sn.get("publishedAt", ""),
            })
        if len(seen) >= max_results:
            break

    ids = list(seen)
    if ids:
        det = _api_get("videos", part="contentDetails,statistics", id=",".join(ids[:50]))
        for item in det.get("items", []):
            c = seen.get(item["id"])
            if not c:
                continue
            cd, st = item["contentDetails"], item.get("statistics", {})
            secs = _iso8601_to_seconds(cd.get("duration"))
            c.update(durationSec=secs, duration=_mmss(secs),
                     views=int(st.get("viewCount", 0)),
                     hasCaptions=cd.get("caption") == "true")
    return list(seen.values())


# ---------------------------------------------------------------- yt-dlp backend


def _ytdlp_json(args: list[str]) -> list[dict]:
    try:
        out = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings",
             "--extractor-args", _EXTRACTOR_ARGS, *args],
            capture_output=True, text=True, timeout=120,
        ).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _search_ytdlp(title: str, max_results: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in (s.format(t=title) for s in _QUERIES[:3]):
        for d in _ytdlp_json([f"ytsearch{max_results}:{q}"]):
            vid = d.get("id")
            if not vid or vid in seen:
                continue
            secs = int(d.get("duration") or 0)
            caps = bool((d.get("subtitles") or {}) or (d.get("automatic_captions") or {}))
            seen[vid] = {
                "videoId": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                "title": d.get("title", ""), "channel": d.get("channel") or d.get("uploader", ""),
                "publishedAt": d.get("upload_date", ""),
                "durationSec": secs, "duration": _mmss(secs),
                "views": int(d.get("view_count") or 0),
                "hasCaptions": caps,
            }
        if len(seen) >= max_results:
            break
    return list(seen.values())


# ---------------------------------------------------------------- public


def search(title: str, *, max_results: int = 6) -> list[dict]:
    if os.environ.get("YOUTUBE_API_KEY"):
        cands = _search_api(title, max_results)
        if cands:
            return _rank(cands, max_results)
    return _rank(_search_ytdlp(title, max_results), max_results)


def details(vid: str) -> dict | None:
    if os.environ.get("YOUTUBE_API_KEY"):
        try:
            res = _api_get("videos", part="contentDetails,statistics,snippet", id=vid)
            items = res.get("items", [])
            if items:
                it = items[0]
                cd, st, sn = it["contentDetails"], it.get("statistics", {}), it["snippet"]
                secs = _iso8601_to_seconds(cd.get("duration"))
                return {
                    "videoId": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": sn["title"], "channel": sn["channelTitle"],
                    "publishedAt": sn.get("publishedAt", ""),
                    "durationSec": secs, "duration": _mmss(secs),
                    "views": int(st.get("viewCount", 0)),
                    "hasCaptions": cd.get("caption") == "true",
                }
        except Exception:
            pass
    rows = _ytdlp_json([f"https://www.youtube.com/watch?v={vid}"])
    if not rows:
        return None
    d = rows[0]
    secs = int(d.get("duration") or 0)
    return {
        "videoId": vid, "url": f"https://www.youtube.com/watch?v={vid}",
        "title": d.get("title", ""), "channel": d.get("channel") or d.get("uploader", ""),
        "publishedAt": d.get("upload_date", ""),
        "durationSec": secs, "duration": _mmss(secs),
        "views": int(d.get("view_count") or 0),
        "hasCaptions": bool((d.get("subtitles") or {}) or (d.get("automatic_captions") or {})),
    }


if __name__ == "__main__":
    import sys

    for c in search(" ".join(sys.argv[1:]) or "Before the Throne of God Above"):
        print(f'{c["duration"]:>6}  cap={str(c.get("hasCaptions")):5}  '
              f'{c.get("views", 0):>10,}  {c["channel"][:28]:28}  {c["url"]}')
