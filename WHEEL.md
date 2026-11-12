# The wheel: FIVES's control room

The wheel is home base for every FIVES window. Windows come out of it and go back into it.
Read with CLAUDE.md, WORKFLOW.md and GESTURES.md; their rules still apply (branch + PR,
small PRs, plain-English PR descriptions, everything goes through actions.py).

```
                    ╭──────────────╮
                  🎵      ✏️      📅
                ⚙️      ●       📧        hover a wedge ▶ it grows + its name pops up
                  🧠        ▢              click        ▶ that window flies into view
                    ╰──────────────╯
```

---

## Phase 1: build it for mouse + keyboard (Claude builds this)

**What it does**
- A round menu with one wedge per FIVES window. Each wedge shows a logo.
- **Hover:** the wedge enlarges (like the macOS Dock's magnification) and the window's name pops up.
- **Click:** that window flies into view and the wheel closes.
- Clicking outside the wheel, or Esc, closes it.

**Opening it**
- A hotkey for now. (Later: Hoyu's open-palm swipe. See phase 2.)
- Every wedge also has a keybind **by position**: Option+1 opens wedge 1, Option+2 wedge 2, and so on.
  The keybinds follow the wheel order, so reordering the wheel changes them too.
- Check the keybinds don't clash with common macOS shortcuts; if they do, propose another modifier.
  Global hotkeys need Input Monitoring (the launcher already asks for it).

**Settings: a WHEEL page**
- A **WHEEL** row in the Settings tab with an **EDIT** button. EDIT takes over the tab with its own
  page, the same pattern as CONNECT SPOTIFY.
- On that page:
  - a **live preview** of the wheel that updates as you change things
  - **reorder** wedges by dragging
  - **[–] / [+]** to remove windows from the wheel or add them back
  - **RESET TO DEFAULT** (the order FIVES ships with, which friends start with)
- Rules:
  - at most **8 wedges** (more makes targets too small to hit by hand); past 8, [+] is grayed out
  - **Settings can be moved but never removed** (otherwise there's no way back to Settings)
  - at least one other wedge besides Settings
- Saved in `settings.json`. Hoyu can change these rules; ask if something is unclear.

**Actions (actions.py)**
- `open_wheel`, `close_wheel`, `open_window(name)`, `hide_window(name)`
- Wheel order and keybinds come from settings, not hard-coded.

**Look**
- FIVES style: blue on near-black, Rajdhani font, blues only. Glow on hover.
- Icons are placeholders until Hoyu makes Clone Wars style ones.

**Not now:** hand gestures, more than 8 wedges, custom icons.

**Done when** Hoyu can open the wheel, hover a wedge (it grows and shows its name), click it to open
that window, use Option+number, and reorder / add / remove wedges in Settings.

**Before coding:** plan it and ask Hoyu anything unclear. If it's big, split it into PRs
(for example: 1. the wheel + actions, 2. keybinds, 3. the Settings page).

---

## Phase 2: the hands (Hoyu designs these, per GESTURES.md)

The new gesture system, as Hoyu has sketched it. Details and tuning are his.

```
 ☝️ one finger         = cursor (like now)
 ✋ open-palm swipe    = open / close the WHEEL   (the only gesture that works the old way)
 🤞 two-finger point   = window mode: point at a FIVES window → it glows faintly and locks on
                         → flick → it goes back into the wheel
```

- The **glow before anything happens** is the undershoot rule built in: you see what's targeted first.
- **Lock-on needs stickiness:** once a window glows, it stays locked for a moment even if the aim
  drifts slightly, so the glow doesn't flicker between windows.
- Picking a wedge by hand: hover with the cursor, then Hoyu's **click gesture** (not chosen yet;
  pinch stays reserved for grabbing windows).
- This replaces today's open-palm flick that shows / hides the music window. Update the gesture
  table in GESTURES.md when it lands.

**Later ideas (not now):**
- A gesture that reopens the **last window you flicked away** (like undo).
- Hand-busy detection (phone in hand) from GESTURES.md applies here too.
