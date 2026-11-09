#!/bin/bash
# Legacy Bible Church: worship guide mirror.
#
# Pastor Todd keeps the worship guides in his own folder on his Mac and saves
# them from Word like always. This copies anything new or changed from that
# folder into the church's shared Google Drive folder within seconds, so the
# team can print the newest one without asking. One way only: his folder is
# the truth, Drive is the copy. Nothing is ever deleted from either side.
#
# Install, once, on his Mac (Google Drive for desktop must already be signed in
# and the Legacy Sunday shortcut added to My Drive):
#
#   bash -c "$(curl -fsSL https://worship.legacybiblechurch.com/scripts/guide-sync.sh)"
#
# It puts a copy of itself in ~/Library/Application Support/LBC, a launch agent
# in ~/Library/LaunchAgents, runs once right away and then every time the
# folder changes (and every two minutes as a safety net). Log:
# ~/Library/Logs/worship-guide-sync.log
#
# Remove:  bash ~/Library/Application\ Support/LBC/guide-sync.sh --uninstall

set -u
LABEL="com.legacybiblechurch.guide-sync"
APPDIR="$HOME/Library/Application Support/LBC"
SELF="$APPDIR/guide-sync.sh"
CONF="$APPDIR/guide-sync.conf"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/worship-guide-sync.log"

say() { printf '%s\n' "$*"; }
log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# ── the sync itself (what the launch agent runs) ─────────────────────────────
do_sync() {
  [ -f "$CONF" ] || { log "no config at $CONF"; exit 1; }
  # shellcheck disable=SC1090
  . "$CONF"
  [ -d "$SRC" ] || { log "source folder missing: $SRC"; exit 1; }
  if [ ! -d "$DST" ]; then
    log "Drive folder not available yet: $DST (is Google Drive running?)"; exit 0
  fi
  # ask iCloud for any file it has offloaded, so the copy is complete
  find "$SRC" -maxdepth 1 -name '.*.icloud' -print0 2>/dev/null | while IFS= read -r -d '' ph; do
    real="${ph%.icloud}"; real="$(dirname "$real")/$(basename "$real" | sed 's/^\.//')"
    brctl download "$real" >/dev/null 2>&1 || true
  done
  out="$(rsync -rt --update --omit-dir-times --no-perms --no-owner --no-group \
          --exclude '.*' --exclude '~$*' --exclude 'Icon?' \
          --itemize-changes "$SRC/" "$DST/" 2>&1)"
  rc=$?
  changed="$(printf '%s\n' "$out" | grep -c '^>f' || true)"
  if [ "$rc" -ne 0 ]; then log "rsync exit $rc: $(printf '%s' "$out" | tail -3 | tr '\n' ' ')"
  elif [ "${changed:-0}" -gt 0 ]; then log "copied $changed file(s): $(printf '%s\n' "$out" | grep '^>f' | sed 's/^>f[^ ]* //' | tr '\n' ';')"
  fi
  exit 0
}

# ── uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST" "$SELF" "$CONF"
  say "Removed. Nothing in Drive or in the Worship Guides folder was touched."
  exit 0
}

case "${1:-}" in
  --sync) do_sync ;;
  --uninstall) do_uninstall ;;
esac

# ── install ──────────────────────────────────────────────────────────────────
say ""
say "Legacy Bible Church · worship guide mirror"
say "──────────────────────────────────────────"

# 1. his Worship Guides folder: the one that holds "LBC Worship Guide" files
SRC=""
while IFS= read -r d; do
  if ls "$d"/*Worship\ Guide* >/dev/null 2>&1; then SRC="$d"; break; fi
done < <(find "$HOME/Documents" "$HOME/Desktop" "$HOME/Library/Mobile Documents/com~apple~CloudDocs" \
            -maxdepth 6 -type d -name 'Worship Guides' 2>/dev/null)
if [ -z "$SRC" ]; then
  say "Could not find a folder named Worship Guides that holds the guides."
  say "Drag the folder from Finder into this window, press Enter:"
  read -r SRC
  SRC="${SRC%/}"; SRC="${SRC//\\ / }"
  [ -d "$SRC" ] || { say "That is not a folder. Stopped."; exit 1; }
fi
say "His folder:   $SRC"
say "              $(ls "$SRC" | grep -c 'Worship Guide') guides in it"

# 2. the church Drive folder, through Google Drive for desktop
DST=""
for d in "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive"/"Legacy Sunday"/"Worship Guides"; do
  [ -d "$d" ] && { DST="$d"; break; }
done
if [ -z "$DST" ]; then
  say ""
  say "Google Drive's Legacy Sunday folder is not on this Mac yet. Two checks:"
  say "  1. Google Drive for desktop is installed and signed in as todd@legacybiblechurch.com"
  say "  2. At drive.google.com, Shared with me, right-click Legacy Sunday, Organize, Add shortcut, My Drive"
  say "Then run this command again."
  exit 1
fi
say "Drive folder: $DST"
say ""
printf 'Press Enter to install (or Ctrl+C to stop): '
read -r _

# 3. put the pieces in place
mkdir -p "$APPDIR" "$HOME/Library/LaunchAgents" "$(dirname "$LOG")"
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then cp "${BASH_SOURCE[0]}" "$SELF"
else curl -fsSL https://worship.legacybiblechurch.com/scripts/guide-sync.sh -o "$SELF"; fi
chmod 755 "$SELF"
printf 'SRC=%q\nDST=%q\n' "$SRC" "$DST" > "$CONF"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$SELF</string><string>--sync</string></array>
  <key>WatchPaths</key><array><string>$SRC</string></array>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL

# 4. first copy, right now, from this Terminal window
say ""
say "Copying the guides to Drive now…"
log "installed. source=$SRC dest=$DST"
bash "$SELF" --sync
# Word's ~$ lock files are not guides and are never copied, so they do not count
n_src="$(ls "$SRC" | grep 'Worship Guide' | grep -vc '^~\$')"; n_dst="$(ls "$DST" | grep 'Worship Guide' | grep -vc '^~\$')"
say "In his folder: $n_src   In Drive: $n_dst"
if [ "$n_src" != "$n_dst" ]; then
  say "Not in Drive yet:"
  diff <(ls "$SRC" | grep 'Worship Guide' | grep -v '^~\$') <(ls "$DST" | grep 'Worship Guide' | grep -v '^~\$') | grep '^<' | sed 's/^< /   /'
  say "Last log lines:"; tail -3 "$LOG" | sed 's/^/   /'
fi

# 5. start the watcher, then judge it by what IT writes, not by old log lines
before="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 6
if tail -n +"$((before + 1))" "$LOG" 2>/dev/null | grep -q 'Operation not permitted'; then
  say ""
  say "One more step. macOS is blocking the background copy from reading his folder."
  say "System Settings, Privacy & Security, Full Disk Access, the + button,"
  say "press Cmd+Shift+G, type /usr/bin/rsync, Open. Also add /bin/bash the same way."
  say "Then run this command once more."
else
  say ""
  say "Done. He saves in Word like always. Drive gets the copy by itself."
  say "Log: $LOG"
fi
