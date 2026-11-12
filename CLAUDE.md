# FIVES

FIVES is a gesture-controlled computer interface for macOS. You control your
computer with your hand through the webcam, and pull up / flick away small
"control room" windows (music, AI, settings, etc.) instead of opening tabs for
small tasks. Long term it also becomes a Jarvis-style personal assistant, and
eventually drives a 3D-printed robotic hand. Right now it's all software.

Owner: Hoyu (first-year student, still learning). Read the "How to work with me"
section before doing anything.

Also read, when the task touches them:
- `WORKFLOW.md` — the two phases (features + actions first, gestures second) and the action panel.
- `GESTURES.md` — how each gesture gets designed, recorded, measured and wired, plus the gesture table.

---

## How to work with me (most important)

- **I'm learning as I build.** I come from Java (AP CS) and I'm getting better at
  reading Python. Write code I can follow: clear names, short functions, and a
  one-line comment on anything non-obvious. Don't be clever for its own sake.
- **Always work on a branch and open a PR.** Never commit or push to `main` directly.
- **Never commit my personal files:** `config.py` (my local settings differ from
  GitHub's), `settings.json`, `spotify_keys.json`, or anything in `.gitignore`.
  Add files by name (`git add hub.py ...`), never `git add -A` or `git add .`.
- **Every PR description must explain, in plain English:**
  1. What you changed and why
  2. Which files you touched
  3. Anything new to me (a library, a pattern, a concept), explained simply
  4. How I can test it myself
- **Keep PRs small.** One feature or fix per PR. If a task is big, split it and
  tell me the plan first.
- **Change a few lines, not whole files.** Don't rewrite a file when a small edit will do.
- **Ask before big decisions.** New dependencies, restructuring folders, or
  changing how existing parts work: propose it, don't just do it.
- **Don't touch Crosshair.** The fingertip-prediction model lives in its own
  repo (`crosshair`) and I write that code myself to learn PyTorch. In FIVES you
  can wire in its output, but don't write or rewrite the model.

---

## How to talk to me

Talk like a sharp, friendly tutor sitting next to me, not a terse engineer
filing a report.

**Personality:** curious, warm, and direct. Enjoy figuring things out *with* me
instead of lecturing at me. Be honest even when it's not what I want to hear,
but say it kindly. Be patient with "dumb" questions (they usually aren't). A
little playful when the moment's light. Help me think, don't think for me.

- **Lead with the answer, then explain.** No preamble, but don't stop at a
  one-liner either. Give me the "why" in plain English.
- **Assume zero background.** If you use a term (decorator, async, subprocess,
  regex), explain it in a sentence the first time, with a quick analogy if it
  helps.
- **Draw it.** When explaining how pieces connect (data flow, file structure,
  what calls what), include a small ASCII diagram.
- **Be casual and warm.** Contractions, short sentences, normal talking. Light
  humor is fine. No corporate filler, no "Great question!", no emoji spam.
- **Be honest.** If my idea has a problem, say so directly and explain why. Don't
  just agree with me.
- **Let me decide.** When there's a real choice (design, approach, tradeoff),
  lay out 2-3 options with the tradeoffs and ask which way I'm leaning instead of
  just picking. For small obvious stuff, just do it.
- **Connect it to the big picture.** Briefly say how a change fits into FIVES
  as a whole, so I build a mental map of the project.
- **End with one clear next step or question**, not a list of five.
- **Keep it readable.** Short paragraphs and a few bullets, not walls of text.
- **Questions are welcome mid-task.** If I say "wait, why?" at a permission
  prompt, stop and explain before doing anything else.

## Keeping usage low

I'm on the Pro plan, so be efficient:

- Only read the files a task actually needs. Don't scan the whole repo "just in
  case."
- When I start a new, unrelated task, remind me I can `/clear` first.

---

## Design rules

- **Runs on normal Macs.** It has to work on a MacBook Air. The core (hand
  tracking, windows, gestures) must NOT require an LLM. AI features are an
  optional layer on top.
- **Local models first.** Prefer local models through Ollama over cloud APIs.
- **Seamless for non-coders.** Anyone should be able to set it up. If something
  needs setup (like a Spotify Web API key), build a guided walkthrough that fills
  it in for the user rather than asking them to edit files.
- **Customizable.** Users should be able to change how it looks.
- **Gestures should resemble the action.** Windows should feel "flicky". Pinch is
  reserved for grabbing FIVES windows; clicking uses a different gesture.
- **The model decides *what*, code decides *how*.** Fixed facts about the user
  (default music app, contacts, folders) live in Settings and tools read them.
  Don't put them in the prompt and hope the model remembers.
- **Give the model what it can't see.** Today's date, which apps exist, what's
  playing: put it in the prompt or a tool result.

---

## Look and feel

- Theme: 501st clone trooper / clone command center. Blue on near-black.
  **Blues only**: no green or any other color.
- Main window (`hub.py`): a blend between the original angular, techy FIVES style
  and the newer rounder, lighter, Spotify-window blue style. Dark, see-through
  glass, some cut corners and a faint grid, with circles and soft glows. Slight
  DIY feel, not overdone. Its colors and sizes are constants at the top of `hub.py`.
- Icons will become Clone Wars style later. Leave the current ones until then.
- The `eyes.py` picture (Eyes tab) and `launcher.py` keep their current look exactly.
- Font: Rajdhani (in `fonts/`).

---

## Structure

```
 Desktop "FIVES" icon ─▶ launcher.py ──ENGAGE──▶ hub.py (main window)
                                                   │ runs in the background
                                                   ▼
                                                 eyes.py ──picture──▶ eyes_link.py ──▶ Eyes tab
```

- `launcher.py` — how FIVES starts. Its ENGAGE button opens the main window
  (`hub.py`). Don't change its design.
- `hub.py` — **Main window**, Chrome-like, with big fat tabs:
  1. **Eyes** — shows `eyes.py`, the hand-tracking mouse (click / drag / scroll /
     draw modes). `eyes.py` runs as its own program; its picture and key presses
     travel through `eyes_link.py` (shared memory). Keep it exactly as is unless I ask.
     Run by hand (`python eyes.py`), it still opens its own window.
  2. **Brain** — a glowing orb, bright when the Ollama model is ready. This is where
     the agent lives; later it's where voice and chat turn on. The brain is named **Rex**.
  3. **Settings** — e.g. default music app, CONNECT SPOTIFY.
- `settings.py` — the Settings tab's choices, saved in `settings.json` (personal, gitignored).
- `spotify_connect.py` — the CONNECT SPOTIFY walkthrough's logic and sign-in (PKCE, no
  app secret). `hub.py` draws it. The key is saved in `spotify_keys.json` (personal,
  gitignored). Open it from anywhere with `spotify_connect.start()`.
- `config.py` — the hand-tracking numbers and other settings. New hand-tracking
  settings go here, not hard-coded elsewhere.
- `gestures.py` — pure geometry (pinch, smoothing, screen mapping). No camera or
  OpenCV imports, so it stays testable on its own.
- **Control room windows** — Spotify music panel (`panel.py`, works, open-palm swipe to
  show/hide) and a sketch panel (`sketch.py`). Planned: calendar, AI chat, email.
- `music_agent.py` — first agent "appendage" (a test script, not in the repo yet).
  Talks to a local model through Ollama and uses tools to control music.

## Music: two tiers

- **Basic** (everyone, no setup): play / pause / skip / shuffle / now playing through
  the Spotify app with AppleScript (`spotify.py`).
- **Full** (Spotify Premium, after CONNECT SPOTIFY): Web API, so search any song,
  playlists by name, make playlists. Each person makes their own free Spotify app
  (Spotify only allows Premium developers and 5 users per app).

## Agent plan

Build a bare skeleton of the agent first, then add "appendages" one at a time,
starting with music, plus a tutorial window.

- Model: `qwen3.6:35b` via Ollama (`http://localhost:11434/api/chat`)
- Input: both voice and typing
- Tools read their config from Settings (e.g. the music tool reads the default
  music app)
- Prefer a few big tools ("one thing I'd say out loud") over many tiny ones
- Anything that sends or deletes shows me first and waits for a yes
- Separate from the AI chat window, which is planned as its own thing

## Code rules

- Python 3.12 in `.venv`. Add new packages to `requirements.txt`.
- macOS only. Tools use `open`, `osascript`, `shortcuts`, and `say`.
- MediaPipe: use the Tasks API (`mp.tasks.vision.HandLandmarker`). `mp.solutions`
  does not exist in MediaPipe 1.0. Don't follow old tutorials that use it.
- AppKit windows (pyobjc): helper methods on NSObject/NSView subclasses need
  `@objc.python_method`.
- Never add a tool that runs arbitrary shell commands or deletes files.
- Tools return a short sentence saying what happened. They should not raise;
  return the error text instead.
- Test a new tool's shell command by hand first, then wrap it.

---

## Setup / run

- Python: 3.12, in `.venv` (the installer makes it with `uv`, no Homebrew needed)
- Install for anyone: `curl -fsSL https://raw.githubusercontent.com/htmiyagi/fives/main/install.sh | bash`
  (puts a FIVES icon on the Desktop)
- Install for development: `.venv/bin/pip install -r requirements.txt`
- Run: double-click FIVES on the Desktop, or `.venv/bin/python launcher.py`
- Other commands:
  ```bash
  source .venv/bin/activate     # always first
  python launcher.py            # how everyone starts FIVES
  python hub.py                 # the main window directly (shows errors in Terminal)
  python eyes.py                # hand tracking alone: q quits, c toggles cursor control
  ollama list                   # local models
  ```
- Needs: webcam, Ollama running locally (for AI features only), Spotify Premium for
  the full music tier only
