# LBC Worship — Handoff

Everything for Sunday-morning lyrics lives on the church website. Nothing to install.

Start here: **https://worship.legacybiblechurch.com**

## The two things a person does

**Before Sunday — Prepare the songs** (`worship-studio.html`)
1. Type a song name in the box on the left.
   - A song we've sung before appears in the list as you type. Pick it — done, it already has its words.
   - A new song: choose **Find "…" on YouTube**. The site searches, listens to the recording, and drafts the words (1–3 min). It then shows the videos it found; click **Use this one** on the one that sounds right. That saves the song for good.
2. Put the songs in order with ▲ ▼. ✕ removes one.
3. Fix any wording by typing in the **Words** box. Blank line = new slide. `[Chorus]` on its own line names a slide (Control only — never shown to the congregation). The right pane shows exactly what the TV will show. **Save.**
4. Click **Ready for Sunday**. It checks every song has words and nothing is unsaved, then publishes the set.

**Sunday morning — Run the service** (`worship-control.html`)
- Open Control on the laptop. Click **Open display** and drag that window to the TV. Control shows a green **Display connected** when the TV window is open.
- ← → or the big buttons move slides. **B** blanks the TV (shows the church logo). **Play on YouTube** opens the song's audio.
- If either window is closed or refreshed by accident, reopen it — it picks up on the same slide.

## One-time setup on each computer that will *prepare* songs

Saving needs permission to write to the website. The Studio walks through it (click **Connect this computer**): create a GitHub token on the church account with **Contents** and **Actions** set to *Read and write* for the `worship` repository, paste it in. Stored only in that browser. Running the service on Sunday needs no setup at all.

## How it works (for whoever maintains it)

- **Song library:** `js/songs-data.js` — every song ever prepared: title, YouTube link, words in labelled blocks. The permanent memory; the Studio writes to it directly through the GitHub API.
- **This Sunday:** `js/worship-songs.js` — the ordered list of song ids. Written by **Ready for Sunday**. Control and Display read only this.
- **Shared logic:** `js/sheet.js` (`LBCSheet`) — the one slide builder used by the Studio preview, Control and Display, plus search and the editor's text format. Sunday depends on nothing outside the site.
- **Finding a new song:** the Studio triggers the GitHub Action `worship-prep.yml` with the song name → `scripts/prep/run.py --song` searches YouTube, fetches the top two candidates' audio **through the residential proxy** (`YT_PROXY` secret — YouTube refuses GitHub's own addresses), and runs the **Exact Lyrics Engine** with three independent listens plus captions and the song's verified library words. Everything happens on GitHub; no church computer is involved. About 1–2 minutes per song.
- **The engine** (`scripts/engine/`): every witness — captions, the library, a previously human-verified recording, three Whisper listens — is aligned to the performance and decided line by line by weighted agreement. Sound-alike mishearings are resolved by the verified words; repeated sections vote; Whisper's instrumental hallucinations are dropped. An LLM never supplies lyrics. Output per line: text, time, confidence, status (verified / check / excluded) and alternatives. Only genuinely ambiguous lines become a "Quick check" in the Studio: the video cues 2 s before the line, the person clicks the right words.
- **Memory:** every Save writes `verified/<videoId>.json` — the human-confirmed words for that exact recording. Adding that video again is instant and final. Raw evidence is cached in `evidence/<videoId>.json` so nothing is transcribed twice.
- **Accuracy is measured:** `python3 scripts/engine/eval.py` scores the engine against the verified library on cached evidence (`tests/engine_report.json`); the `Lyrics engine accuracy` workflow fails any engine change that lowers it. Current: known songs 2.8% word errors per line, 96% of lines found, ~1 flagged line per song; unknown songs ~5% word errors with breath-based line breaks.
- **Control ↔ Display:** `BroadcastChannel('lbc-worship')` in the same browser, state mirrored in `localStorage` so a refresh resumes.

### The proxy (the one paid thing)
IPRoyal residential proxy, pay-per-GB, account `legacybiblechurchadmin@gmail.com`. A song costs ~5 MB, so 2 GB ≈ 400 songs. When the dashboard shows it running low, buy more; the credentials don't change. Test it any time: Actions → **yt-diag** → Run workflow → look for `PROXY OK`. If the proxy ever fails, finds still complete using captions/library and the draft says "Unclear" rather than inventing words.

### Optional: a listener machine instead of the proxy
`scripts/helper/setup.sh` on any always-on Mac runs the same engine locally for drafts still marked `needsAudio`. Not needed while the proxy is set.

### Secrets (GitHub → Settings → Secrets → Actions)
`YOUTUBE_API_KEY` (search; keyless yt-dlp search is the fallback) · `SUPADATA_API_KEY` (captions — one witness among several; its free tier has a monthly limit, after which the engine simply runs without captions) · `GROQ_API_KEY` (the Whisper listens — the important one) · `YT_PROXY` (`http://USER:PASS@geo.iproyal.com:12321`, from the IPRoyal dashboard).

### When a song comes back "Unclear" or with many checks
The candidate card says why in plain words. Usual causes: the listener Mac is off (the draft waits, marked "listening"), the recording is a live/echoey one, or the video is a different arrangement from the library. Pick the other candidate video, answer the checks by ear, or open the Words box and fix a line — every fix is remembered for that exact recording.

### Old pieces, kept for compatibility
`worship-prep.html` redirects to the Studio. The Google-Sheet-driven schedule in `worship-prep.yml` is commented out; `scripts/prep/sheet.py` remains only because `run.py` reuses its `Row` type.
