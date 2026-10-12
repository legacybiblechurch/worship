# The livestream overlay

> **The stream now runs in OBS on the worship laptop.** Setup is in `OBS-SETUP.md`; Sunday is `/obs/`. OBS captures this same page from a green window Control opens, so nothing below about PRISM is needed unless the iPad is the encoder again.

The TV shows lyrics and the laptop plays the songs. The YouTube stream comes from the iPad, which sees neither. One web page fixes the lyrics half. It loads once as a web widget in PRISM and then runs itself.

**Hand-off page for whoever runs the stream:** https://worship.legacybiblechurch.com/stream/setup/
It has the address, a Copy button, the three taps, and a live preview. Nothing else is needed.

**The page itself:** `worship-stream.html`, short address `worship.legacybiblechurch.com/stream/` (the setup page shows it without `https://`, because PRISM's URL box already starts with that)

## What it does

- **Sunday before 10:30 AM** — a full-screen card: the logo drawn on, "Service begins shortly", the time, and a countdown for the last hour. At 10:30 it fades out by itself (after a 15-second grace, since the iPad's clock and the room's never quite agree). If the service runs late the stream simply shows the room until it starts, like any other livestream.
- **While Control has a slide up** — the words, full screen on black, like the TV. The pulpit is empty while we sing, so there is nothing worth keeping from the camera. Between slides only the text fades; the black stays, so the camera never flashes through mid-song. PRISM's editor cannot reach its own buttons once a widget covers the whole screen, so stretch it as far as PRISM allows; a sliver of camera at one edge is the trade-off, and `mode=panel` is there if that ever bothers anyone.
- **During the sermon** — the preacher stays in the picture. The title, then each point, sits in a bar at the bottom left with a gold edge, like a broadcast caption. A song after the sermon goes back to full black.
- **Otherwise** — nothing. The page is transparent and the camera shows through.
- **Any other day** — the card shows for 20 seconds after the page loads, so whoever is setting it up sees it worked, then the camera.

Nobody operates it. It follows Worship Control through the church's room code, the same relay the phone remote uses.

## The room code

There is one fixed code for the church, `ROOM` in `js/sheet.js`. Control publishes under it, and the phone remote and this page listen to it, so nobody types a code anywhere. If it ever has to change, change it there: every page follows. (Control used to make a random code per browser, which meant typing it into PRISM. That is gone.)

## Setup in PRISM

Give the setup page above to whoever runs the stream. The steps are: My Studio → Widget → Web → paste the address → name it Lyrics → Save → stretch it over the whole picture → Lock layer. Tested on an iPhone: the page is see-through, the words are readable, the widget can be hidden and shown with a tap, and slides follow Control.

Still to confirm on the iPad itself: that PRISM keeps the widget between sessions, so Sunday is just "open PRISM, go live".

## Options (add to the address with ?, then & between them)

Only for testing. The hand-off address has none.

- `test=1` always show a sample slide, ignore Control (also skips the card on a weekday)
- `debug=1` a status box: room, relay, songs, last slide heard, words, card, music
- `in=MINUTES` rehearse the card: pretend the service starts that many minutes from now
- `hold=0.25` minutes the card stays up after the start time (15 s by default)
- `intro=20` seconds the card shows on a day with no service (`intro=0` for none)
- `pin=1` the card never fades
- `card=0` no card at all, words only
- `at=10:30` the service time, 24-hour clock
- `mode=panel` big words on a dark panel in the middle, everything else transparent, so the widget can be any size
- `mode=lower` a lower third over the camera
- `third=sermon` which items use the bottom-left bar instead of full screen: `sermon` by default, `sermon,scripture` to put readings there too, `none` for full screen always
- `test=sermon` a sample sermon bar, to see the look
- `room=CODE` listen to a different room code
- `bg=green` / `bg=solid` a green or black background, if PRISM ever cannot do a transparent page
- `music=ADDRESS` play an audio file while the card is up, `vol=0.5` its volume. PRISM may silence sound from a web widget; its own music mixer is the safer route. Mind copyright: YouTube checks livestreams, so use public-domain or licensed music and keep the licence note.

## What to know

- It reads this Sunday's songs fresh on every load. If the set or the words are republished while it is open, it notices within 90 seconds and reloads itself.
- A page opened mid-service picks up the slide Control is on, if that was within the last two hours.
- If the laptop or the relay is offline the words stay on the last slide. Reload the widget to clear it.
- `debug=1` says which half is wrong when the words do not show.

## Song audio (not this page)

Plan: a small USB mixer between the iPad and the room. The shirt mic receiver into one channel, the laptop's audio into another, one USB feed to the iPad. The laptop plays to the TV and the mixer at once through a Multi-Output Device in Audio MIDI Setup. During songs pull the shirt mic fader down so the TV does not echo through it.

Not tested yet: whether PRISM on the iPad accepts the mixer as its audio input.

Fallback: PRISM Live Studio on the Mac with the iPad as the camera through PRISM Lens, lyrics by window capture and song audio through BlackHole.
