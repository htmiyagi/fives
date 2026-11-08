# Install FIVES (one command)

For a Mac. Takes about 5 minutes, mostly downloading. No password needed.

## 1. Paste this into Terminal

Open **Terminal** (Cmd + Space, type "Terminal", Enter), paste this line, and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/htmiyagi/fives/main/install.sh | bash
```

A window asks **Install FIVES?** Click **Install**. When it's done, click **Open FIVES**.
That's the only time you type anything.

## 2. The FIVES window

From now on, **double-click FIVES on your Desktop**. You get a small window:
**Start FIVES**, **Set up permissions**, **Settings**, **Update**.

The first time, click **Set up permissions**. FIVES pops up Apple's own boxes and opens the right
Settings page for each one, so you just turn **Terminal** on:

- **Camera**: so FIVES can see your hand
- **Accessibility**: so it can move the mouse and click
- **Input Monitoring**: so the keyboard shortcuts work from any app

Then **quit Terminal completely (Cmd + Q)** and double-click FIVES again. macOS only applies new
permissions after a restart.

## Using it

- Press `c` in the camera window to turn hand control on or off. Press `q` to quit.
- **Point** with your index finger to move the cursor. **Pinch** thumb + index and let go to click.
  Pinch and move to drag. All the gestures are in the [README](README.md#hand-mouse-gestures).
- Press `l` to cycle the cursor "lead": `STEADY` / `CNN` (small neural networks that predict where your
  finger is going), `DAMPED` (a simple physics guess), or `OFF`. They were trained on one person's hand,
  so tell Hoyu how they feel for you!

## Updating

Click **Update** in the FIVES window (or paste the command from step 1 again). Your settings are kept.

## If something goes wrong

- **The camera window is black**: quit FaceTime, Zoom, Photo Booth or anything else using the camera,
  then Cmd + Q Terminal and start FIVES again.
- **The cursor doesn't move**: check Accessibility is on for Terminal, and press `c` in the camera window.
- **"CNN lead not loaded"**: FIVES still works with the simpler lead. Send Hoyu the message it printed.
