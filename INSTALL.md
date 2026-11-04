# Install FIVES (one command)

For a Mac. Takes about 5–10 minutes, mostly downloading.

## 1. Paste this into Terminal

Open **Terminal** (Cmd + Space, type "Terminal", Enter), paste everything below, and press Enter.
It may ask for your Mac password once (that's Homebrew installing). Typing a password shows nothing on screen; that's normal.

```bash
command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"; \
brew install python@3.12 git && \
git clone https://github.com/yagiht/fives.git ~/fives && \
cd ~/fives && \
"$(brew --prefix)/bin/python3.12" -m venv .venv && \
source .venv/bin/activate && \
pip install --upgrade pip && \
pip install -r requirements.txt pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-CoreText pillow && \
echo "" && echo "FIVES is installed. Starting it now..." && \
python eyes.py
```

## 2. Allow the permissions

The first time, macOS will ask (or silently block) a few things. Open **System Settings > Privacy & Security**
and turn **Terminal** ON in each of these:

- **Camera**: so FIVES can see your hand
- **Accessibility**: so it can move the mouse and click
- **Input Monitoring**: so the keyboard shortcuts work from any app

Then quit FIVES (press `q` in its window) and start it again (step 3).

## 3. Running it again later

```bash
cd ~/fives && source .venv/bin/activate && python eyes.py
```

## Using it

- Press `c` in the camera window to turn hand control on or off. Press `q` to quit.
- **Point** with your index finger to move the cursor. **Pinch** thumb + index and let go to click.
  Pinch and move to drag. All the gestures are in the [README](README.md#hand-mouse-gestures).
- Press `l` to cycle the cursor "lead": `CNN` (default, a small neural network that predicts where
  your finger is going), `DAMPED` (a simple physics guess), or `OFF`. It was trained on one person's
  hand, so tell Hoyu whether it feels good for you!

## If something goes wrong

- **"command not found: python3.12"** or Homebrew errors: close Terminal, open a new one, paste the command again.
- **"destination path '~/fives' already exists"**: it's already installed; use step 3.
- **The cursor doesn't move**: check Accessibility (step 2) and press `c` in the camera window.
- **"CNN lead not loaded"**: FIVES still works with the simpler lead. Send Hoyu the message it printed.
