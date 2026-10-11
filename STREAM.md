# Lyrics on the livestream

The TV shows lyrics and the laptop plays the songs. The YouTube stream comes from the iPad, which sees neither. This page puts the lyrics on the stream. The song audio is a separate piece (bottom of this file).

## What it is

`worship-stream.html` draws only the words, bottom centre, on a clear background. It follows Worship Control the same way the phone remote does, through the room code. When Control is blank or between songs it draws nothing and the camera shows through. Nobody operates it.

Short address: `https://worship.legacybiblechurch.com/stream?room=CODE`

## One-time setup

1. On the laptop open **Control**. Click **Phone remote**. Note the 6-letter code.
2. The address is `https://worship.legacybiblechurch.com/stream?room=` followed by that code.
3. In PRISM on the iPad add a **Web Browser** widget with that address. Stretch it across the bottom third of the picture.
4. Check it with `&test=1` on the end first. That keeps a sample slide up whatever Control is doing. Look for three things:
   - the camera shows through the page (transparent)
   - the words are readable over the live picture
   - the widget can be hidden and shown with a tap
5. Take `&test=1` off. Open Control and move a slide. The words appear on the stream. Press **B** and they disappear.

## Options (add to the address with &)

- `room=CODE` the room code from Control
- `test=1` always show a sample slide
- `debug=1` a small status box (room, relay connected, songs loaded, last slide heard)
- `bg=green` a plain green background for a chroma key filter, if PRISM has one
- `bg=solid` a solid black bar, if PRISM cannot do a transparent page. Then the widget has to be hidden between songs by hand.

## What to know

- It reads this Sunday's songs fresh on every load. If the set or the words are republished while it is open, it notices within 90 seconds and reloads itself.
- A page opened mid-service picks up the slide Control is on, but only if that was within the last two hours.
- It uses the same free relay as the phone remote (ntfy.sh). If the laptop or the relay is offline the lyrics stay on the last slide. Reload the widget to clear it.
- The room code is saved in Control's browser. If that browser's data is cleared Control makes a new code and the address above stops working. Open the status box (`debug=1`) when the lyrics do not show. It says which half is wrong.
- Not tested yet: how PRISM's web widget treats transparency and sizing. That is what step 4 is for.

## Song audio (not this page)

Plan: a small USB mixer between the iPad and the room. The shirt mic receiver goes into one channel and the laptop's audio into another. The mixer sends one USB feed to the iPad. The laptop plays to the TV and the mixer at once through a Multi-Output Device in Audio MIDI Setup. During songs pull the shirt mic fader down so the TV does not echo through it.

Not tested yet: whether PRISM on the iPad accepts the mixer as its audio input.

Fallback for both: PRISM Live Studio on the Mac with the iPad as the camera through PRISM Lens. Lyrics by window capture and song audio through BlackHole.
