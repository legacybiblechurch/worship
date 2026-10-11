# The livestream: lyrics and the starting-soon screen

The TV shows lyrics and the laptop plays the songs. The YouTube stream comes from the iPad, which sees neither. These two pages put them on the stream. Both load in PRISM as web widgets. PRISM allows four web widgets, so there is room for both.

- **Lyrics** shows the words whenever Worship Control has a slide up
- **Starting soon** covers the camera before the service and fades away on its own

Song audio is a separate piece (bottom of this file).

## 1. Lyrics

`worship-stream.html` follows Worship Control the same way the phone remote does, through the room code. When a slide is up it shows the words. When Control is blank or between songs it draws nothing and the camera shows through. Nobody operates it.

Short address: `https://worship.legacybiblechurch.com/stream/?room=CODE`

**Full screen is the default.** While we sing the pulpit is empty because the pastor sits down. Full screen puts the words centred on black across the whole frame, big and easy to read, like the TV. If you would rather keep the camera in view, add `&mode=lower` for a lower third over the picture.

### One-time setup

1. On the laptop open **Control**. Click **Phone remote**. Note the 6-letter code.
2. The address is `https://worship.legacybiblechurch.com/stream/?room=` followed by that code.
3. In PRISM on the iPad add a **Web Browser** widget with that address. For full screen, stretch it over the whole picture. For `mode=lower`, stretch it across the bottom third.
4. Check it with `&test=1` on the end first. That keeps a sample slide up whatever Control is doing. Look for three things:
   - when no slide is up, the camera shows through (the page is transparent)
   - the words are readable
   - the widget can be hidden and shown with a tap
5. Take `&test=1` off. Open Control and move a slide. The words appear on the stream. Press **B** and they disappear.

### Options (add to the address with &)

- `room=CODE` the room code from Control
- `mode=lower` a lower third over the camera instead of full screen
- `test=1` always show a sample slide
- `debug=1` a small status box (room, relay connected, songs loaded, last slide heard)
- `bg=green` a plain green background for a chroma key filter, if PRISM has one
- `bg=solid` a solid black background, if PRISM cannot do a transparent page. Then the widget has to be hidden between songs by hand.

### What to know

- It reads this Sunday's songs fresh on every load. If the set or the words are republished while it is open, it notices within 90 seconds and reloads itself.
- A page opened mid-service picks up the slide Control is on, but only if that was within the last two hours.
- It uses the same free relay as the phone remote (ntfy.sh). If the laptop or the relay is offline the lyrics stay on the last slide. Reload the widget to clear it.
- The room code is saved in Control's browser. If that browser's data is cleared Control makes a new code and the address above stops working. Add `&debug=1` when the lyrics do not show. The status box says which half is wrong.
- Not tested yet: how PRISM's web widget treats transparency. That is what step 4 is for.

## 2. Starting soon

`worship-soon.html` is a full-screen card: the logo drawn on, "Service begins shortly", the service time and a countdown for the last hour. At the service time it says "We are about to begin" for two minutes, then fades out by itself and the camera shows through. Nobody has to hide it.

Short address: `https://worship.legacybiblechurch.com/soon/`

Add it as a second web widget stretched over the whole picture, and put it **above** the lyrics widget. It needs no room code. It works from the clock: Sundays at 10:30 AM Pacific. On any other day it just shows a plain card with no countdown and never fades.

### Rehearse it

Add `?in=1` and it pretends the service starts in one minute. Then you can watch the whole sequence: countdown, "about to begin", fade. Use `?in=1&debug=1` to see what it thinks.

### Options

- `at=10:30` the service time, 24-hour clock
- `in=MINUTES` rehearsal: pretend the service starts that many minutes from now
- `hold=2` minutes to stay up after the start time
- `pin=1` never fade (useful while testing)
- `music=ADDRESS` play an audio file while the card is up. It loops, then fades out with the card
- `vol=0.5` music volume from 0 to 1
- `debug=1` status box

## Music before the service

Two ways. Test which works.

1. **PRISM's own music.** PRISM can mix music into a broadcast on its own, so it does not depend on a web widget. The app lists built-in tracks and a My Studio area for your own. Check the Media overlay in the app.
2. **The card plays it.** Add `&music=` with the address of an audio file. Test it first: add `&debug=1` and see whether the box says `playing` and whether people watching a test stream actually hear it. A web widget may be silenced or blocked from playing sound, and nothing here can check that from outside the iPad.

**Be careful what you play.** YouTube checks livestreams for copyrighted music. Commercial worship albums or anything from a streaming service can get the stream muted, blocked or the replay silenced. Use music that is public domain or licensed for this, and keep the licence note. Plain piano hymns from before 1930 are the usual safe choice, but check the recording as well as the song. The recording has its own copyright.

## Song audio during the service (not these pages)

Plan: a small USB mixer between the iPad and the room. The shirt mic receiver goes into one channel and the laptop's audio into another. The mixer sends one USB feed to the iPad. The laptop plays to the TV and the mixer at once through a Multi-Output Device in Audio MIDI Setup. During songs pull the shirt mic fader down so the TV does not echo through it.

Not tested yet: whether PRISM on the iPad accepts the mixer as its audio input.

Fallback for both: PRISM Live Studio on the Mac with the iPad as the camera through PRISM Lens. Lyrics by window capture and song audio through BlackHole.
