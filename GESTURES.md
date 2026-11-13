# FIVES gestures: how phase 2 works

Phase 1 (features and actions) is far enough along. Music works and is done for now.
This file is how the hand-gesture phase gets done. Read it with CLAUDE.md and WORKFLOW.md;
their rules still apply (branch + PR, small PRs, plain-English explanations, never commit
config.py / settings.json / spotify_keys.json).

---

## Whose part this is

Gestures are the technical heart of FIVES, and they're **Hoyu's**, like the Crosshair model.

```
 Hoyu                                        Claude
 ─────                                       ──────
 designs each gesture (shape, motion,        explains concepts from zero
   what it does, how it should feel)         reviews his code and his numbers
 decides thresholds and tuning               builds the TOOLS: recorder, replay tester,
 records the data, judges the feel             live debug view, scoreboards
 says when a gesture is "done"               wires a finished gesture to its action
```

- **Don't design, tune or train a gesture for him unless he asks.** When he asks "what
  should this be?", lay out 2-3 options with tradeoffs and ask which way he's leaning.
- **Ask at the start of each gesture how much of the detection code he wants to write
  himself.** Don't assume.
- Tools around the gesture (recording, testing, measuring, displaying) are fair game for
  Claude to build, in small PRs.

---

## Rules every gesture follows

- **It maps to an action, nothing else** (the action panel in WORKFLOW.md). A gesture never
  reaches into a feature's code directly.
- **It resembles the action.** Windows should feel "flicky". Skip feels like a flick forward.
- **Pinch is reserved for grabbing FIVES windows.** Clicking uses a different gesture.
- **Undershoot, never overshoot.** A missed gesture is annoying. A gesture that fires by
  itself is worse. When in doubt, nothing happens.
- **Every gesture has:** a clear starting hand shape, a minimum size/speed, a cooldown, and
  its settings in `config.py` (one line each, with a comment saying what raising or lowering it does).
- **No collisions.** Before adding a gesture, check it can't be confused with an existing one
  (list them in the gesture table below). Each new gesture ships with a test that the old ones
  still don't fire on it.
- **Works on a MacBook Air.** No LLM involved, cheap enough to run every frame.
- **Geometry stays in `gestures.py`** (pure math, no camera or OpenCV), so it can be tested on recordings.

---

## How one gesture gets made (one at a time)

Make one gesture really good before starting the next. Don't open five half-done ones.

```
 1. DESIGN    Hoyu writes a short note: what it does, the hand shape + motion,
              how it should feel, what it must NOT be confused with.
 2. RECORD    Hoyu records himself: the gesture done right (many times, different
              speeds, both hands if relevant) AND normal hand use that should NOT trigger it
              (typing, reaching, resting, waving at a friend, pointing at things).
 3. BUILD     a first detector (simple rules first: shapes, distances, speeds, timing).
              A learned model only if rules can't get there, and only when Hoyu decides.
 4. MEASURE   replay every recording through the detector and score it (see below).
 5. TUNE      Hoyu adjusts the settings, measure again. Repeat.
 6. FEEL      Hoyu uses it live for real work. Blind comparisons where possible.
 7. WIRE      connect it to its action. Small PR.
 8. DONE      when it meets its targets (below) and Hoyu says it feels right.
```

### Measuring (every gesture, every change)

The same idea as the phantom-click analysis: replay saved recordings through the real
detector code, so a change can be checked in seconds and compared fairly.

- **False triggers per minute**: on the "should NOT trigger" recordings. The most important number.
- **Hit rate**: on the "done right" recordings, what share fired.
- **Lag**: from the moment the motion completes to the action firing.
- **Feel**: Hoyu's rating, blind when two versions are being compared.

Starting targets (Hoyu can change these): **under 1 false trigger per 10 minutes of normal
use**, **at least 9 of 10 real attempts**, and lag he doesn't notice.

Recordings live in a local, gitignored folder (hand landmark points only, never camera images),
so they can be replayed any time a detector changes.

---

## Tools to build first (Claude can build these)

1. **Gesture recorder**: press a key, do the gesture (or normal stuff), it saves the hand
   points with a label ("skip", "not a gesture").
2. **Replay scorer**: runs every recording through a detector and prints the four numbers above,
   plus which recordings it got wrong.
3. **Live debug view**: in the EYES tab, shows what the detector sees right now (shape found?
   how far along the motion? why it didn't fire: "too slow", "fingers not straight").

---

## The gesture table

Keep this up to date. It's how collisions get avoided.

| gesture | hand shape + motion | action | status |
|---|---|---|---|
| flick | open palm, swipe left / right | open / close the wheel (or put the sketch away when pointing at it) | works; settings `FLICK_*` |
| point | ✌️ index + middle out, aim at a FIVES window | lock on (window glows faintly); pauses the wheel swipe | works; settings `POINT_*` |
| finger flick | ✌️ held still, then index + middle snap sideways (palm stays still) | while locked on: put that window away. Undo: stay in ✌️, stop, finger-flick back within `POINT_UNDO_SECONDS` (palm swipes and hand moves don't undo) | works; settings `FINGER_FLICK_*`, score with `score_gestures.py` |
| pinch | thumb + index together | grab FIVES windows (reserved) | exists for clicking today; to be moved to grabbing |
| skip | not decided yet | skip | **next: Hoyu designs it** |
| previous / replay | not decided yet | previous / restart | after skip |
| spin | ☝️ index fingertip draws a fast circle (~250° in 0.8 s), round, not tiny; off in draw mode. Not ✌️: a ✌️ circle looked like a finger flick | ↺ counterclockwise: restart the song (Spotify only; nothing + a Terminal message if Spotify isn't open). ↻ clockwise never fires | detector built, prints only; two ways to measure (`SPIN_METHOD`), compare with `score_gestures.py spin-compare`; record spins with Ctrl+Option+S. Hoyu tunes, then wire. Settings `SPIN_*` |

Note: `config.py` sets `FLICK_DISTANCE` three times (1.6, then 1.2, then 0.7) and the last one
wins. Clean that up (with Hoyu's say on the value) before adding more swipes.

---

## Ideas already on the table (Hoyu decides)

- **Telling gestures apart:** by hand shape (for example two fingers ✌️ swipe = skip / previous),
  by where you point (point at the music window, then swipe), or by motion (a small ↺ circle =
  replay). Mixing these is fine.
- **Pause:** a "stop" hand held still is natural but fires by accident easily, so it would need
  a long hold or a second step.
- **Hand-busy detection** (later): if a hand is holding something (start with phones, using
  object detection like YOLO), ignore that hand and use the other one, or pause. High confidence,
  several frames in a row, "when in doubt the hand is free". Exceptions to decide later (for
  example a pen in draw mode).
- **Windows by hand:** grab, move, snap left / right, flick away. The window actions need to
  exist and move smoothly first (WORKFLOW.md).
