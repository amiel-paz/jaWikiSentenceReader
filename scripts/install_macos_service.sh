#!/bin/sh

set -eu

LABEL="com.amielpaz.ja-wiki-sentence-reader"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON="$PROJECT_DIR/.venv/bin/python"
TEMPLATE="$PROJECT_DIR/launchd/$LABEL.plist"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
TARGET="$AGENTS_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ ! -x "$PYTHON" ]; then
  echo "Missing virtual environment Python: $PYTHON" >&2
  echo "Create the environment and install the project before installing the service." >&2
  exit 1
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"
install -m 0644 "$TEMPLATE" "$TARGET"

plutil -remove ProgramArguments.0 "$TARGET"
plutil -insert ProgramArguments.0 -string "$PYTHON" "$TARGET"
plutil -replace WorkingDirectory -string "$PROJECT_DIR" "$TARGET"
plutil -replace StandardOutPath -string "$LOG_DIR/ja-wiki-sentence-reader.log" "$TARGET"
plutil -replace StandardErrorPath -string "$LOG_DIR/ja-wiki-sentence-reader.error.log" "$TARGET"
plutil -lint "$TARGET"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$TARGET"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo "Installed and started $LABEL"
echo "Reader: http://127.0.0.1:5001"
echo "Logs: $LOG_DIR/ja-wiki-sentence-reader.log"
