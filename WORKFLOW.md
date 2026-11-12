# FIVES workflow: features first, gestures second

This is how FIVES gets built from now on. Read it together with CLAUDE.md.
CLAUDE.md's rules still apply in both phases (branch + PR, small PRs, explain in
plain English, never commit config.py / settings.json / spotify_keys.json).

```
 PHASE 1 (now)                                   PHASE 2 (later)
 features + actions, as fast as possible   ──▶   gestures that drive those actions
 Claude builds, Hoyu decides the layout          Hoyu designs, records, trains, measures
```

---

## The big idea: everything is an action

Every feature exposes **named actions**: plain functions with a short name and a
one-line description, collected in one place (the "action panel"). Anything that
triggers a feature goes through an action, never straight into the feature's code.

```
          keyboard key    button in a window    Rex (voice / typing)    gesture (phase 2)
                 \               |                     |                    /
                  ▼              ▼                     ▼                   ▼
            ┌──────────────────────── ACTION PANEL ─────────────────────────┐
            │ show_music  hide_music  skip  pause  grab_window  move_window │
            │ flick_away  start_listening  delete_playlist ...              │
            └────────────────────────────────┬──────────────────────────────┘
                                              ▼
                                    the features themselves
```

Why: in phase 2, adding a gesture means mapping it to an existing action
("open-palm swipe → hide_music"). No feature code changes. If a feature is wired
as "this key does this thing", it has to be dug up and rewired later.

### Rules for actions

- One action = one thing a person would want ("skip", "flick_away"), not an internal step.
- Each action has a name, a one-line description, and simple inputs (no hidden state).
- Actions return a short sentence saying what happened, and never raise: return the error text instead
  (same as the tool rules in CLAUDE.md).
- Rex's tools and the action panel should line up: a Rex tool is usually just an action
  the model can call. Don't build the same thing twice.
- Risky actions (send, delete) still go through the confirm box (confirm_box.py), whoever triggers them.
- **Windows must be movable by code**: show, hide, move_to(x, y), resize, flick_away, with smooth
  animation. Phase 2's hand control drives exactly these, so they need to be good.

Where the panel lives (file name, how actions register) is a design decision:
propose it before building it.

---

## Phase 1: features and actions (now)

Goal: get the layout of the whole FIVES operation right, fast. Speed matters more
than polish here, since the hands come later.

- Build features quickly, in small PRs, each one exposing its actions.
- Convert existing keyboard shortcuts and buttons to actions as features get touched
  (for example eyes.py's c / m / h keys, the music panel, the Settings buttons).
- Hoyu's job in this phase: **decide what exists and how it's laid out** (which windows,
  which tabs, what each does, how they fit together). Ask him for those decisions;
  don't guess at layout.
- Claude's job: build the features and tools. Hoyu doesn't need to spend brainpower on
  how a tool works inside, only on what it does and where it lives.
- Keep a running list of actions in the panel's file so Hoyu can see everything FIVES can do.

Phase 1 is done when Hoyu says the layout feels right: every feature he wants exists
and can be triggered by a key, a button or Rex.

---

## Phase 2: gestures (Hoyu's part)

This is the technical heart of FIVES and it's Hoyu's work, like the Crosshair model:

- **Hoyu designs, records, trains and tunes the gestures.** Claude can explain, review,
  build data-collection and testing tools, and wire a finished gesture to an action.
  Don't design or train gestures for him unless he asks.
- Gestures should resemble the action (windows feel "flicky"; pinch is reserved for
  grabbing FIVES windows; clicking uses a different gesture).
- Each gesture maps to an action in the panel, nothing else.
- Measure every gesture, the way the cursor-lead study was measured:
  - false triggers per minute (fired when he didn't do it)
  - misses (he did it and nothing happened)
  - lag (hand moves → window moves)
  - how it feels, rated blind where possible
- Undershoot rather than overshoot: a missed gesture is annoying, a false one is worse.
- Planned: hand-busy detection (object detection, starting with phones). If a hand is
  holding something, ignore it and use the other hand, or pause. High confidence +
  confirm frames, and "when in doubt, the hand is free". Exceptions to decide later
  (for example a pen in draw mode).
