# The stream in OBS — one-time setup

The stream runs from the worship laptop in OBS. Camera, shirt mic, song words, countdown and videos all meet there, and nothing crosses the internet except the stream itself. Sunday for whoever runs it is on **https://worship.legacybiblechurch.com/obs/** — check the picture, press Start Streaming.

This file is the one-time build. About half an hour.

## What is already made

In this repo, `obs/`:

- `Legacy_Stream.json` — the scene collection. Two scenes:
  - **Service**: Camera, the green lyrics window keyed out, the shirt mic, Chrome's audio (the songs).
  - **Video**: the QuickTime window and QuickTime's audio. No mic, so the room's copy of the video never echoes under the stream's.
- `profile/basic.ini` — 1080p, 30 fps, Apple hardware encoder, 4500 kbps.
- `profile/service.json` — YouTube, no key (you add the account).

On the church laptop these are already in place in OBS's folder. On any other Mac: Scene Collection → Import → `obs/Legacy_Stream.json`, then Profile → Import → `obs/profile`.

## How the words get in with no internet in the loop

Control has an **Open stream window** button next to Open display. It opens the overlay page on a green background. That window follows Control inside the same browser, exactly like Display does. OBS captures that window and keys out the green. Words on black during a song, the countdown before the service, nothing (so, camera) the rest of the time. No relay, nothing cached, nothing to rate-limit. The phone remote still uses the relay; the stream does not.

## The build

1. **Open OBS.** First launch asks about camera, microphone and screen-recording permission: allow all three. If an Auto-Configuration Wizard appears, **Cancel** it; the profile is already set. Check the top-right menus say Scene Collection **Legacy Stream** and Profile **Legacy Stream**. If not, pick them.

2. **Camera.** In the Service scene, double-click **Camera** and choose the device. The iPad through PRISM Lens until the real camera arrives; later, the PTZ.

3. **The green window.** In Chrome open **Worship Control** and click **Open stream window**. Back in OBS, double-click **Lyrics (green window)** and in the Window list pick *Stream lyrics — Legacy Bible Church*. The preview shows the countdown over the camera, or just the camera, depending on the day and the hour. Put a slide up in Control and the words appear. Press B and they go.
   - Green fringe around letters? Right-click the source → Filters → Chroma Key → raise Similarity a little.

4. **Mic.** Plug the Lark USB-C receiver into the Mac. Double-click **Mic (shirt mic)** and choose it. Speak; the Mic meter bounces.

5. **Songs.** Double-click **Songs (Chrome audio)** and make sure the application is Google Chrome. Press Play on a song in Control; the Songs meter bounces. If OBS asks for screen-recording permission here, allow it; app audio capture uses it.

6. **YouTube.** Settings → Stream → Service: YouTube → **Connect Account**, sign in as the church. Then Start Streaming offers **Manage Broadcast**, which creates the YouTube event with a title. (Or paste a stream key from YouTube Studio instead; both work.)

7. **Test stream.** Start Streaming with the broadcast set to Unlisted or Private. Watch it on a phone: picture, countdown, words, song audio, mic. Stop.

8. **Video.** Open any video in QuickTime. In OBS click the **Video** scene; double-click **Video (QuickTime window)** and pick the QuickTime window; same for **Video sound**. Play the video; picture and meter move. Click **Service** to come back.

That's the build. Nothing in it is weekly.

## Every Sunday (what the /obs/ page says)

- The person on the words: Control, Open display, Open stream window.
- The person on the stream: open OBS, see the room and the countdown, Mic meter bounces, Start Streaming. During a video: click Video, then Service. After: Stop Streaming.

## Settings reference

- Base and output 1920×1080, 30 fps. Encoder Apple VT H264 hardware, 4500 kbps. Audio 160 kbps, 48 kHz.
- Scene transition Fade, 300 ms.
- The green window is `worship-stream.html?bg=green`. Any of that page's options still apply (see STREAM.md): `&card=0` for no countdown, `&mode=lower` for a lower third.

## If something is wrong

- **No countdown, no words:** the green window isn't open, or OBS lost it. Open stream window in Control, then re-pick the window in the Lyrics source.
- **Words show but the camera doesn't come back after a song:** the chroma key filter is off or the key colour isn't green. Filters on the Lyrics source.
- **Mic meter dead:** the receiver isn't the chosen device, or macOS denied microphone permission to OBS (System Settings → Privacy & Security → Microphone).
- **Songs meter dead:** screen-recording permission (same place), or the Songs source points at the wrong app.
- **Stream drops:** Settings → Output → lower bitrate to 3000. Wired internet if there is any.

## Later

- **Sermon title and points** as a lower third, typed in the Studio — the next build.
- **Advanced Scene Switcher** (free OBS plugin) can switch to Video when QuickTime goes full screen and back when it closes, removing the two clicks.
- The PTZ camera for the building: plugs in by USB, replaces the Camera device, nothing else changes.
