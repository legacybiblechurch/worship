#!/bin/bash
# One-time setup for the church Mac that "listens" to recordings.
# Installs a private Python 3.12 (no admin rights needed) with yt-dlp, and a
# launchd job that runs the helper every minute while the Mac is on.
set -euo pipefail
LBC="$HOME/.lbc"; mkdir -p "$LBC"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

if [ ! -x "$LBC/py/bin/python3" ]; then
  echo "Installing a private Python 3.12 into $LBC/py ..."
  url=$(curl -s https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest \
        | python3 -c 'import json,sys,re; a=[x["browser_download_url"] for x in json.load(sys.stdin)["assets"] if re.search(r"cpython-3\.12\.\d+\+\d+-aarch64-apple-darwin-install_only\.tar\.gz$", x["name"])]; print(a[0])')
  curl -sL -o "$LBC/py.tgz" "$url" && tar xzf "$LBC/py.tgz" -C "$LBC" && mv "$LBC/python" "$LBC/py" && rm "$LBC/py.tgz"
fi
"$LBC/py/bin/python3" -m pip install -q -U yt-dlp requests

if [ ! -f "$LBC/engine.env" ]; then
  echo "GROQ_API_KEY=" > "$LBC/engine.env"; chmod 600 "$LBC/engine.env"
  echo "!! Put the Groq API key in $LBC/engine.env (GROQ_API_KEY=...)"
fi

PLIST="$HOME/Library/LaunchAgents/church.lbc.helper.plist"
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>church.lbc.helper</string>
  <key>ProgramArguments</key><array>
    <string>$LBC/py/bin/python3</string>
    <string>$REPO_DIR/scripts/helper/lbc_helper.py</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LBC/helper.log</string>
  <key>StandardErrorPath</key><string>$LBC/helper.log</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/bin:/bin:/usr/local/bin</string></dict>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Helper installed. Log: $LBC/helper.log"
