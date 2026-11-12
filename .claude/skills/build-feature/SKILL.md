---
name: build-feature
description: Build one FIVES feature from its feature file on its own, test it, audit it, fix the real problems, and open a PR. Use when Hoyu says "build-feature" plus a feature file (for example "build-feature WHEEL.md phase 1 part 1").
---

# build-feature: build → test → audit → fix → audit → PR

Hoyu hands you a feature file (like WHEEL.md) and which part to build. You build it without
stopping to ask, check your own work, and leave him a PR to review. Follow CLAUDE.md,
WORKFLOW.md and GESTURES.md the whole way.

## Scope

- Build only the part Hoyu named. If he didn't name one, build the smallest useful first slice
  and list the rest as next steps in the PR.
- If the change is getting big (roughly 400+ lines), stop at a sensible point, open the PR for what
  works, and list the rest as next steps. Small PRs beat one huge one.

## Hard rules

- Work on a new branch (`claude/<feature>-<part>`). Never commit to or push `main`. Never merge.
- Add files by name. Never commit `config.py`, `settings.json`, `spotify_keys.json`, or anything gitignored.
- **No real side effects while testing:** don't play / pause / change Spotify, don't send anything,
  don't delete anything, don't open other apps. Use fakes or the code's test hooks.
- **Never turn on the webcam.** Don't run `hub.py`, `launcher.py` or `eyes.py`: `hub.py` starts
  `eyes.py` (webcam) and warms up Ollama the moment it opens.
- **Ollama only if the feature file says `Ollama: allowed`.** Without that line, fake the model
  (`mock.patch` on `ollama.chat`, like `test_brain.py`). With it, you may talk to the real model,
  but **every tool stays faked**: the model "runs" a tool, the fake just records the call. Real-model
  tests skip unless `FIVES_REAL_MODEL=1` is set (`@unittest.skipUnless(...)`), so the normal test run
  never needs Ollama.
- **Never use screen recording or screenshots of the screen** (`screencapture` etc.). Hoyu doesn't allow it.
  To see a window, draw it into an image yourself (see "Looking at it").
- **Don't design or tune gestures.** That's Hoyu's (GESTURES.md). Hook up actions so gestures can be
  added later.
- Everything a user can trigger goes through actions.py (WORKFLOW.md).

## Decisions

Don't stop to ask. Make the reasonable choice and **write it down** for the PR.
- If the feature file already decides something, follow it exactly.
- Layout and look choices are Hoyu's (WORKFLOW.md). If the file doesn't decide one, pick something
  simple, keep it easy to change (a constant at the top of the file), and flag it in the PR under
  "LAYOUT CALLS FOR HOYU".
- Only stop early if you're truly blocked: something irreversible, a new dependency, or a change to
  how an existing part works that the feature file doesn't cover. Then open a draft PR with your
  question at the top.

## Steps

1. **Read** CLAUDE.md, WORKFLOW.md, the feature file, and only the code the feature touches.
2. **Plan** in a few lines: files to add or change, actions to add, tests to write. Put this plan at
   the top of the PR.
3. **Build** in small commits with clear messages.
4. **Test it yourself:**
   - Write tests for the logic (math, settings saving, order, keybind mapping, actions). Run all the
     repo's tests, not just new ones. Tests use `unittest` (no pytest), as `test_*.py` in the repo root:
     `.venv/bin/python -m unittest discover -p "test_*.py" -v`
     If the feature file says `Ollama: allowed`, also run it once with `FIVES_REAL_MODEL=1` in front
     and put the real model's results (which tool it picked for each phrase) in the PR.
   - **Smoke test:** start the feature's own window or module on its own, with a timeout (never
     `hub.py`, see Hard rules). Check it opens without errors and quits cleanly. Read what it printed.
     If the feature only lives inside `hub.py`, build just its view in a small script and render it
     (below) without starting the hub.
   - **Looking at it:** render the window's view into a PNG and look at the image. In AppKit:
     `rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())`,
     `view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)`,
     then save `rep.representationUsingType_properties_(4, None)` (4 = PNG) to a file.
     Render the important states (for the wheel: closed, open, a wedge hovered). Save renders in a
     gitignored folder (for example `renders/`, add it to .gitignore if needed). Don't commit them.
   - If a test keeps failing after 3 honest attempts at a fix, stop and explain in the PR.
5. **Audit:** run the `auditor` agent on the feature.
6. **Fix** only what the audit marks MUST FIX or SHOULD FIX. Leave nitpicks.
7. **Audit once more.** Then **stop**, even if nitpicks remain. Two audits, no more.
8. **Open the PR.**

## The PR description

Plain English, as CLAUDE.md asks:

```
WHAT THIS DOES        what changed and why, in a few sentences
FILES TOUCHED         list
NEW TO YOU            any library, pattern or concept, explained simply
PLAN                  the plan from step 2
DECISIONS I MADE      every choice you made without asking
LAYOUT CALLS FOR HOYU layout/look choices he should confirm or change (and where the constant is)
TESTS                 what's tested, results
WHAT IT LOOKS LIKE    which states you rendered and what you saw (renders are in renders/, not committed)
AUDIT 1               the auditor's report
AUDIT 2               the auditor's report after fixes
CHECK BY HAND         the auditor's hand-check list, plus anything about feel you couldn't judge
NEXT STEPS            what's left of the feature
```
