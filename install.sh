#!/bin/bash
# Install (or update) FIVES on a Mac. No Homebrew, no password.
#   curl -fsSL https://raw.githubusercontent.com/htmiyagi/fives/main/install.sh | bash
# The FIVES window's Update button runs it with --no-launch (no pop-up windows, just update).
#
# What it does:
#   1. asks "Install FIVES?" in a normal Mac window
#   2. installs "uv" (a small tool that installs Python itself) into your home folder, if you don't have it
#   3. downloads FIVES into ~/fives (keeping your config.py if you're updating)
#   4. makes FIVES's own Python 3.12 and installs what it needs (a few minutes the first time)
#   5. puts a FIVES icon on your Desktop: double-click it to open the FIVES window from now on
set -e

REPO="https://github.com/htmiyagi/fives"
DIR="$HOME/fives"
QUIET=0
[ "$1" = "--no-launch" ] && QUIET=1

say() { printf '\n\033[1;36m%s\033[0m\n' "$1"; }

ask() {   # a real Mac window with buttons (AppleScript is built into every Mac). Prints the button clicked.
  osascript - "$1" "$2" "$3" <<'APPLESCRIPT' 2>/dev/null || true
on run argv
  set {msg, b1, b2} to argv
  return button returned of (display dialog msg with title "FIVES" buttons {b1, b2} default button b2)
end run
APPLESCRIPT
}

# 1. ask first
if [ "$QUIET" = 0 ]; then
  answer="$(ask "Install FIVES?

Hand tracking for your Mac: point at the screen to move the mouse, pinch to click.

It downloads about 1 GB and takes about 5 minutes. No password needed." "Cancel" "Install")"
  [ "$answer" = "Install" ] || { echo "Cancelled."; exit 0; }
fi

# 2. uv
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  say "Installing uv (it installs Python for FIVES)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

# 3. the code
if [ -d "$DIR/.git" ] && command -v git >/dev/null 2>&1 && git -C "$DIR" rev-parse >/dev/null 2>&1; then
  say "Updating FIVES (git)..."
  git -C "$DIR" pull --ff-only || say "(couldn't update with git; keeping your copy as it is)"
else
  say "Downloading FIVES..."
  TMP="$(mktemp -d)"
  curl -fsSL "$REPO/archive/refs/heads/main.zip" -o "$TMP/fives.zip"
  unzip -q "$TMP/fives.zip" -d "$TMP"
  mkdir -p "$DIR"
  if [ -f "$DIR/config.py" ]; then cp "$DIR/config.py" "$TMP/config.keep"; fi    # keep your settings
  cp -R "$TMP"/fives-main/. "$DIR"/
  if [ -f "$TMP/config.keep" ]; then cp "$TMP/config.keep" "$DIR/config.py"; fi
  rm -rf "$TMP"
fi

# 4. Python + packages
cd "$DIR"
say "Setting up Python 3.12 and FIVES's packages (a few minutes the first time)..."
[ -x .venv/bin/python ] || "$UV" venv --python 3.12 .venv
"$UV" pip install --python .venv/bin/python -r requirements.txt \
  pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-CoreText pyobjc-framework-AVFoundation \
  pyobjc-framework-ApplicationServices pillow

# 5. the Desktop icon: double-click = the FIVES window (start/stop, permissions, settings, update)
printf '#!/bin/bash\ncd "$HOME/fives" || exit 1\n.venv/bin/python launcher.py\n' > "$HOME/Desktop/FIVES.command"
chmod +x "$HOME/Desktop/FIVES.command"

say "FIVES is installed!"
if [ "$QUIET" = 0 ]; then
  answer="$(ask "FIVES is installed!

From now on, double-click FIVES on your Desktop to open it.

The first time, click 'Set up permissions' in the FIVES window." "Later" "Open FIVES")"
  if [ "$answer" = "Open FIVES" ]; then open "$HOME/Desktop/FIVES.command"; fi
fi
