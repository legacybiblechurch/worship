"""
Reconcile a rough transcript of a specific YouTube performance against known-good
reference lyrics, and emit clean slide-ordered lyrics for that performance.

The transcript (especially auto-captions / Whisper) is unreliable on *words* but reliable
on *what is actually sung and in what order, including repeats*. The reference lyrics are
reliable on words. This step fuses the two.

LLM provider is picked from the environment, first one wins:
    ANTHROPIC_API_KEY  -> Claude              (best on this exactness task)
    GEMINI_API_KEY     -> Google Gemini       (free tier)
    GROQ_API_KEY       -> Llama 3.3 70B / Groq (free tier, same key as Whisper)

Output dict: { "lyrics": [ {"label","lines"} ], "order": str, "confidence": int, "notes": str }
"""

from __future__ import annotations

import json
import os
import re

from http_util import post_json

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
GROQ_LLM_MODEL = os.environ.get("GROQ_LLM_MODEL", "openai/gpt-oss-120b")

SYSTEM = """You prepare worship lyrics for a church that projects them on a screen while \
the congregation sings along to a specific YouTube recording. The projected words must \
match THAT recording exactly - same sections, same order, same number of repeats - or the \
room sings out of time.

You are given:
- the song title
- REFERENCE LYRICS: trustworthy wording, but NOT necessarily this recording's structure
- TRANSCRIPT: timestamped lines from this exact recording. If auto-generated it will have \
wrong words, missing punctuation and run-on lines, but it usually shows which sections are \
sung, in what order, and how many times each repeats. If the transcript is too sparse or \
garbled to determine structure, say so in notes and fall back to the reference's own order.

Produce the lyrics for THIS recording:
- Follow the TRANSCRIPT for structure: which verses/choruses/bridges are sung, their \
order, and every repeat.
- Be CONSERVATIVE about repeats. Only add a repeated section when the transcript clearly \
shows that section's actual lines appearing again in that spot. Do NOT infer a repeat from \
a few stray or garbled words. A short run of repeated words at the end of a section is a \
TAG or vamp of just those lines - not a repeat of the whole section.
- When auto-captions are too garbled to tell how a section repeats, fall back to the \
REFERENCE's own section order and repeat structure, and lower your confidence. Never \
output the same multi-line section three or more times unless the transcript unmistakably \
shows it.
- Use the REFERENCE for wording. Where the transcript's words disagree with the reference, \
trust the reference - unless the transcript clearly shows a different or extra line the \
reference lacks, in which case transcribe it as best you can and flag it in notes.
- Segment into labelled blocks: "Verse 1", "Verse 2", "Chorus", "Bridge", "Refrain", \
"Tag", "Intro". Reuse the same label when a section recurs.
- If a single line is repeated on its own for emphasis (a vamp), output it as its own \
one-line block, once per repeat.
- FORMAT every line for the screen: one short sung phrase per line, about 6 words / 40 \
characters, matching the line length of the rest of the song. Never put two phrases on one \
line. If a HUMAN CORRECTION supplies run-on text, break it into proper lines the same way. \
Sentence case - capitalise the first word of each line and words naming God ("God", "Lord", \
"Christ", "You", "Your", "Him", "His", "Thee", "Thy") - do not random-capitalise other words.
- No leading/trailing blank lines. No "[Music]" markers. Straight apostrophes.
- If REFERENCE LYRICS are absent, reconstruct from the transcript plus your own knowledge \
of the song, and lower your confidence.

confidence: 90-100 = reference song, clean human captions, obvious structure. \
70-89 = reference song, auto-captions, structure mostly clear and matches the reference. \
40-69 = no reference, or transcript too messy to confirm structure (you fell back to the \
reference order). below 40 = guessing.
Do not give 90+ confidence when the transcript source is auto-generated captions.

Return ONLY minified JSON with keys: lyrics, order, confidence, notes.
lyrics is an array of {label, lines}. lines is an array of strings."""


# ---------------------------------------------------------------- prompt


def _cue_block(transcript: dict, limit: int = 400) -> str:
    lines = []
    for c in transcript.get("cues", [])[:limit]:
        t = c["text"].strip()
        if t and not re.fullmatch(r"\[[^\]]*\]", t):
            lines.append(f'[{c["t"]:.0f}s] {t}')
    return "\n".join(lines)


def _reference_block(reference: list[dict] | None) -> str:
    if not reference:
        return "(none - not in the church library; use your own knowledge of the song)"
    out = []
    for b in reference:
        out.append(f'{b.get("label") or "-"}:')
        out.extend(f"  {ln}" for ln in b["lines"])
    return "\n".join(out)


_IS_DESCRIPTION = "description"


def build_prompt(title, reference, transcript, fixes=""):
    src = {"subs": "human-written captions",
           "whisper": "Whisper transcription of the audio",
           "asr": "YouTube auto-generated captions",
           "description": "the lyrics pasted in the video's DESCRIPTION box "
                          "(words only - NO timing, NO repeats, NOT the performance order)"
           }.get(transcript.get("source"), "captions")
    parts = [
        f"SONG: {title}",
        f"\nTRANSCRIPT SOURCE: {src}",
        f"\nREFERENCE LYRICS:\n{_reference_block(reference)}",
        f"\nTRANSCRIPT (this recording, in order):\n{_cue_block(transcript)}",
    ]
    if transcript.get("source") == _IS_DESCRIPTION:
        parts.append(
            "\nIMPORTANT: the text above is the song's lyrics from the description, not a "
            "transcript of this performance. You do NOT know which sections this recording "
            "sings or how often they repeat. Output the song in its standard/common structure, "
            "set confidence no higher than 50, and in notes say clearly that every section and "
            "repeat must be checked against the video."
        )
    if fixes.strip():
        parts.append(f"\nHUMAN CORRECTIONS (these override everything above):\n{fixes.strip()}")
    parts.append("\nReturn the minified JSON now.")
    return "\n".join(parts)


# ---------------------------------------------------------------- providers


def _call_gemini(prompt: str, key: str, *, system: str = SYSTEM) -> str:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={key}")
    res = post_json(url, json_body={
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "temperature": 0.2, "maxOutputTokens": 8192},
    }, timeout=150)
    cand = (res.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))


def _call_anthropic(prompt: str, key: str, *, system: str = SYSTEM) -> str:
    res = post_json("https://api.anthropic.com/v1/messages", json_body={
        "model": ANTHROPIC_MODEL, "max_tokens": 4000, "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }, headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=150)
    return "".join(p.get("text", "") for p in res.get("content", []))


def _call_groq(prompt: str, key: str, *, json_mode: bool = True, system: str = SYSTEM) -> str:
    body = {
        "model": GROQ_LLM_MODEL, "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    res = post_json("https://api.groq.com/openai/v1/chat/completions",
                    json_body=body, headers={"Authorization": f"Bearer {key}"},
                    timeout=150)
    return res["choices"][0]["message"]["content"]


def _llm_once(prompt: str, *, json_mode: bool = True, system: str = SYSTEM) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_anthropic(prompt, os.environ["ANTHROPIC_API_KEY"], system=system)
    if os.environ.get("GEMINI_API_KEY"):
        return _call_gemini(prompt, os.environ["GEMINI_API_KEY"], system=system)
    if os.environ.get("GROQ_API_KEY"):
        return _call_groq(prompt, os.environ["GROQ_API_KEY"], json_mode=json_mode, system=system)
    raise RuntimeError("set ANTHROPIC_API_KEY, GEMINI_API_KEY or GROQ_API_KEY")


_last_call = [0.0]
_MIN_GAP = float(os.environ.get("LLM_MIN_GAP_SECONDS", "4"))


def _llm(prompt: str, *, system: str = SYSTEM) -> str:
    """Retry on rate-limits; on a JSON-mode generation failure, retry free-form."""
    import time

    from http_util import HTTPError

    gap = _MIN_GAP - (time.time() - _last_call[0])
    if gap > 0:
        time.sleep(gap)

    delay = 8
    for attempt in range(5):
        try:
            out = _llm_once(prompt, system=system)
            _last_call[0] = time.time()
            return out
        except HTTPError as e:
            _last_call[0] = time.time()
            transient = e.status in (429, 500, 502, 503, 529)
            json_fail = e.status == 400 and "generate JSON" in e.body
            if json_fail:
                return _llm_once(prompt + "\n\nRespond with ONLY the JSON object, no other text.",
                                 json_mode=False, system=system)
            if not transient or attempt == 4:
                raise
            m = re.search(r'"?retry.?after"?[:\s"]+([0-9.]+)', e.body, re.I)
            wait = float(m.group(1)) if m else delay
            time.sleep(min(wait + 1, 65))
            delay = min(delay * 2, 60)
    raise RuntimeError("llm retries exhausted")


# ---------------------------------------------------------------- public


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def reconcile(title: str, reference: list[dict] | None, transcript: dict,
              fixes: str = "") -> dict:
    out = _extract_json(_llm(build_prompt(title, reference, transcript, fixes)))
    lyrics = []
    for b in out.get("lyrics", []):
        lines = [str(x).strip() for x in b.get("lines", []) if str(x).strip()]
        if lines:
            lyrics.append({"label": str(b.get("label", "")).strip(), "lines": lines})
    if not lyrics:
        raise ValueError("reconcile produced no lyrics")
    conf = out.get("confidence", 0)
    try:
        conf = int(conf)
    except (TypeError, ValueError):
        conf = 0
    order = out.get("order", "")
    if isinstance(order, list):
        order = " · ".join(str(x) for x in order)
    cap = 50 if transcript.get("source") == _IS_DESCRIPTION else 100
    return {"lyrics": lyrics, "order": str(order),
            "confidence": max(0, min(cap, conf)), "notes": str(out.get("notes", ""))}


_FROM_TITLE_SYSTEM = """You lay out worship lyrics for a church that projects them on a screen, \
segmented into labelled blocks ("Verse 1", "Verse 2", "Chorus", "Bridge", "Tag").

If HUMAN LYRICS are given, keep their WORDS and their ORDER - do not add, drop, substitute or \
rephrase any words. But present them properly for the screen:
- start each line with a capital letter; capitalise names and "God", "Lord", "You"/"Your" \
  when they refer to God; use straight apostrophes
- fix only obvious spelling slips ("dear"->"deer", "herarts"->"hearts", "yeild"->"yield")
- break the text into natural sung lines - one short phrase per line, about 4 lines per block
- group the lines into the song's real sections and label them
Set confidence 90.

Otherwise write the song's lyrics from your own knowledge of that title, in the common \
performance order; if you are unsure you know the exact song, still give your best attempt \
and set confidence 25-40.

No leading/trailing blank lines, no "[Music]" markers.
Return ONLY minified JSON: {lyrics:[{label,lines}], order, confidence, notes}."""


_SUPPLIED_HINT = re.compile(r"(instead|use these|change (all|the) lyrics|here are the|actual lyrics|correct lyrics|:\s*\n)", re.I)


def from_title(title: str, fixes: str = "") -> dict:
    """Brand-new song whose video has no captions: lyrics from the model's knowledge,
    or verbatim from the person's Fixes text if they pasted the lyrics there."""
    fixes = (fixes or "").strip()
    supplied = bool(fixes) and (len(fixes) > 160 or bool(_SUPPLIED_HINT.search(fixes)))
    prompt = "SONG: " + title
    if fixes:
        prompt += ("\n\nHUMAN LYRICS (keep the words/order, format for the screen):\n" if supplied
                   else "\n\nHUMAN CORRECTIONS:\n") + fixes
    prompt += "\n\nReturn the minified JSON now."
    out = _extract_json(_llm(prompt, system=_FROM_TITLE_SYSTEM))
    lyrics = []
    for b in out.get("lyrics", []):
        lines = [str(x).strip() for x in b.get("lines", []) if str(x).strip()]
        if lines:
            lyrics.append({"label": str(b.get("label", "")).strip(), "lines": lines})
    if not lyrics:
        raise ValueError("from_title produced no lyrics")
    try:
        conf = int(out.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0
    lo, hi = (75, 95) if supplied else (20, 45)
    note = ("Lyrics you typed into Fixes, laid out into slides - give them a final read."
            if supplied else
            "Lyrics from general knowledge - no captions on this video. Check every line "
            "and section against the video before Sunday.")
    return {"lyrics": lyrics, "order": str(out.get("order", "")),
            "confidence": max(lo, min(hi, conf)), "notes": str(out.get("notes", "")) or note}


if __name__ == "__main__":
    import sys

    from lib_songs import load_songs
    from transcript import fetch_transcript

    slug = sys.argv[1] if len(sys.argv) > 1 else "before-the-throne-of-god-above"
    song = load_songs()[slug]
    tr = fetch_transcript(song["youtube"], allow_audio="--audio" in sys.argv)
    if not tr:
        raise SystemExit("no transcript")
    print(json.dumps(reconcile(song["title"], song["lyrics"], tr), indent=2, ensure_ascii=False))
