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

On any Mac: Scene Collection → Import → `obs/Legacy_Stream.json`, then Profile → Import → `obs/profile`.

**The church's media laptop is Windows.** Its files are in `obs/windows/`: the same two scenes with Windows sources (DirectShow camera, Windows window capture, WASAPI mic, Application Audio Capture for Chrome, Display Capture for the TV, desktop audio for a video) and a profile with the x264 software encoder at 720p so a laptop without a graphics card keeps up. The Windows build is its own section below. The Mac steps are kept for the Mac.

## On the Windows laptop (the church's media laptop)

About half an hour, once, by someone who can sign in to the church YouTube.

1. **Install OBS** from obsproject.com (OBS 30 or newer). First launch: if the Auto-Configuration Wizard appears, **Cancel** it.
2. **Get the two files.** On GitHub open `obs/windows/Legacy_Stream.json`, click the download icon, and do the same for `obs/windows/profile/basic.ini` and `obs/windows/profile/service.json` (put those two in a folder called `Legacy_Stream`). In OBS: **Scene Collection → Import** → the json. **Profile → Import** → the folder. Then pick both from those menus so the top bar says Legacy Stream twice.
3. **Chrome, once.** Chrome stops drawing a window that is completely covered by other windows, and OBS would stream a frozen frame. Right-click the Chrome icon on the taskbar → right-click **Google Chrome** → **Properties**. In **Target**, after the closing quote, add a space and `--disable-backgrounding-occluded-windows`. OK. Close every Chrome window and open Chrome from that taskbar icon from now on. (Same flag on the desktop shortcut if that is what gets used.)
4. **The green window.** In Chrome, Worship Control → **Open the stream window**. It pops up as its own window. Leave it open; it can sit behind Control and OBS. Never minimize it. In OBS double-click **Lyrics (green window)**, Window: pick *[chrome.exe]: Stream lyrics — Legacy Bible Church - Google Chrome*, Capture Method **Windows 10 (1903 and up)**, Window Match Priority **Window title must match**. The main preview shows the countdown or the words over black with the green keyed out. (On Windows 10 a yellow border may show around a captured window on the laptop's own screen; it is not in the stream.)
5. **Camera.** Double-click **Camera**, pick the device. A USB webcam, or the iPad through PRISM Lens for PC if that is what the church has. Resolution 1920x1080 if offered.
6. **Mic.** Plug the Lark USB-C receiver in. Double-click **Mic (shirt mic)**, pick it. Speak; the Mic meter bounces.
7. **Songs.** Double-click **Songs (Chrome audio)**: Window: any *chrome.exe* entry, Match Priority **Executable name must match**. Press Play on a song in Control; the Songs meter lights. Pull its fader to about −10 dB.
8. **YouTube.** Settings → Stream → Service YouTube → **Connect Account**, sign in as the church.
9. **Video.** Click the **Video** scene. Double-click **Video (the TV screen)**, pick the TV's display. **Video sound (desktop audio)** is already the laptop's output, so whatever plays on the laptop is heard. Gear under the mixer → **Advanced Audio Properties** → Video sound: Track **1** ticked, Monitoring **Monitor Off**. Click **Service**.
10. **Test stream**, Unlisted. Picture, countdown, words, a song, the mic, the sermon bar. Stop.

Then the Sunday card at `/obs/` is the same on either laptop. The TV window works the same on Windows: drag it to the TV, click it once, it fills the TV.

## How the words get in with no internet in the loop

Control has an **Open stream window** button next to Open display. It opens the overlay page on a green background. That window follows Control inside the same browser, exactly like Display does. OBS captures that window and keys out the green. Words on black during a song, the countdown before the service, a bottom-left bar with the title or the point during the sermon (the preacher stays in the picture), nothing (so, camera) the rest of the time. No relay, nothing cached, nothing to rate-limit. The phone remote still uses the relay; the stream does not.

## The build

1. **Open OBS.** First launch asks about camera, microphone and screen-recording permission: allow all three. If an Auto-Configuration Wizard appears, **Cancel** it; the profile is already set. Check the top-right menus say Scene Collection **Legacy Stream** and Profile **Legacy Stream**. If not, pick them.

2. **Camera.** In the Service scene, double-click **Camera** and choose the device. The iPad through PRISM Lens until the real camera arrives; later, the PTZ.

3. **The green window.** In Chrome open **Worship Control** and click **Open stream window**. It opens as its own small window. Click into it and press **Ctrl+Cmd+F** so it fills a screen with no address bar; it moves to its own desktop and keeps running out of sight. Back in OBS, double-click **Lyrics (green window)** and in the Window list pick *[Google Chrome] Stream lyrics — Legacy Bible Church*, then **Restart capture**. The dialog's own preview shows the raw window (words on black, or plain green); the main preview behind it has the green keyed out. Put a slide up in Control and the words appear over the camera. Press B and they go.
   - If the capture shows Control or another page, OBS is still on an old window: pick *Stream lyrics* in the list again and Restart capture.
   - Green fringe around letters? Right-click the source → Filters → Chroma Key → raise Similarity a little.

4. **Mic.** Plug the Lark USB-C receiver into the Mac. Double-click **Mic (shirt mic)** and choose it. Speak; the Mic meter bounces.

5. **Songs.** Double-click **Songs (Chrome audio)** and make sure the application is Google Chrome. Press Play on a song in Control; the Songs meter lights. It runs hot, so pull the Songs fader in the mixer down until the song peaks in the yellow, about −10 dB. Leave Control's own slider alone; that one is the room. (OBS never plays its mix back to you. The meter is the proof; the test stream is the ear.) If OBS asks for screen-recording permission here, allow it; app audio capture uses it.

6. **YouTube.** Settings → Stream → Service: YouTube → **Connect Account**, sign in as the church. Then Start Streaming offers **Manage Broadcast**, which creates the YouTube event with a title. (Or paste a stream key from YouTube Studio instead; both work.)

7. **Test stream.** Start Streaming with the broadcast set to Unlisted or Private. Watch it on a phone: picture, countdown, words, song audio, mic. Stop.

8. **Video.** Open any video in QuickTime. In OBS click the **Video** scene and double-click **Video (QuickTime window)**.
   - With the TV plugged in: set **Method** to **Display Capture** and choose the TV. The scene then shows whatever the TV shows, so a full-screen QuickTime clip, and no window ever needs picking again.
   - Without a TV (testing): keep Window Capture and pick the QuickTime window. Its name is the file's name, so this has to be re-picked per file; fine for a test, not for Sundays.
   Play the video and watch the **Video sound** meter light. Then the gear under the mixer → **Advanced Audio Properties**: on the Video sound row, Track **1** must be ticked and Audio Monitoring **Monitor Off**. The first build missed Track 1 and the stream got picture with no sound. Click **Service** to come back.

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
- **A meter lights but the phone hears nothing:** Advanced Audio Properties, that row, Track 1 ticked and Monitor Off. If it is the recap video, YouTube can also mute copyrighted music on a live stream in real time; the live dashboard says so.
- **Stream drops:** Settings → Output → lower bitrate to 3000. Wired internet if there is any.

## Never commit the live profile

Once a YouTube account is connected, OBS writes the account's OAuth tokens into the profile's `basic.ini` under `[YouTube]`. That file on the laptop is a credential. `obs/profile/basic.ini` in this repo holds only the settings sections (General, Video, Output, SimpleOutput, Audio, Stream1); copy those by hand if they change, never the whole file. GitHub's push protection blocked exactly this on 2026-10-11.

## Proven

Built and tested on 2026-10-11 on the church MacBook Pro (M5), OBS 32.0.1, on an unlisted YouTube stream: words from Control keyed over the camera, blank and unblank, song audio, the shirt mic, and a QuickTime clip with sound. `obs/Legacy_Stream.json` in this repo is the collection OBS saved after that test, device picks included.

## Later

- **Advanced Scene Switcher** (free OBS plugin) can switch to Video when QuickTime goes full screen and back when it closes, removing the two clicks.
- The PTZ camera for the building: plugs in by USB, replaces the Camera device, nothing else changes.
