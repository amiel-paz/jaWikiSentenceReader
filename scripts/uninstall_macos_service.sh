#!/bin/sh

set -eu

LABEL="com.amielpaz.ja-wiki-sentence-reader"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
if [ -e "$TARGET" ]; then
  rm "$TARGET"
fi

echo "Stopped and removed $LABEL"
echo "Existing logs remain in $HOME/Library/Logs."
