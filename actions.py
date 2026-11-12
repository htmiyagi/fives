"""
actions.py - the action panel: one list of everything FIVES can do.

Every way of triggering a feature (a key, a button, Rex, a gesture) goes through here, so a new
trigger only has to name an action. Nothing calls the feature's code directly.

    key  /  button  /  Rex  /  gesture
              │
              ▼
    actions.run("hide_music")  ──▶  ACTIONS["hide_music"].run()  ──▶  the feature
              ▲
    GESTURES["flick_right"] = "hide_music"     (a gesture is just one line in that table)

Rules (same as Rex's tools in CLAUDE.md): an action does one thing a person would want, has a
short name and a one-line description, and returns one short sentence. It never raises.

Try it:   .venv/bin/python actions.py        (prints the whole list)
"""

from dataclasses import dataclass, field
from typing import Callable

import wheel_logic     # just the wheel's list of windows and rules (no AppKit), so it's cheap to import


@dataclass(frozen=True)
class Action:
    """One thing FIVES can do. frozen=True means it can't be changed after it's made."""
    name: str
    description: str
    run: Callable[..., str]
    inputs: dict = field(default_factory=dict)   # input name -> what it means ({} = takes nothing)


ACTIONS: dict[str, Action] = {}    # the registry: name -> Action. Filled in by @action below.


def action(name: str, description: str, inputs: dict | None = None):
    """Decorator: put the function under it into ACTIONS. (Same idea as @tool in tools.py.)"""
    def register(fn):
        if name in ACTIONS:
            raise ValueError(f"Two actions are both called '{name}'.")   # a typo here should fail loudly, at startup
        ACTIONS[name] = Action(name, description, fn, inputs or {})
        return fn
    return register


def run(name: str, **inputs) -> str:
    """Do an action by name. Always returns a sentence, even when something goes wrong."""
    found = ACTIONS.get(name)
    if found is None:
        return f"FIVES has no action called '{name}'."
    try:
        return found.run(**inputs)
    except Exception as err:            # an action must never crash whatever triggered it
        return f"Something went wrong in {name}: {err}"


# ---------------------------------------------------------------------------
# Gestures -> actions. A new gesture is one line here. "gesture@window" means
# "only while pointing at that window", and wins over the plain gesture.
# ---------------------------------------------------------------------------
GESTURES = {
    "flick_right": "hide_music",              # open-palm swipe right (config.FLICK_HIDE)
    "flick_left": "show_music",               # ...and back the other way
    "flick_right@sketch": "put_away_sketch",  # pointing at the sketch window: either swipe puts it away
    "flick_left@sketch": "put_away_sketch",
    # "fist": "pause",                        # <- how a music gesture will look once one exists
}


def action_for(gesture: str, window: str | None = None) -> str | None:
    """Which action a gesture means, or None. Checks the window-specific line first."""
    if window and f"{gesture}@{window}" in GESTURES:
        return GESTURES[f"{gesture}@{window}"]
    return GESTURES.get(gesture)


# ---------------------------------------------------------------------------
# Windows. eyes.py starts them, so it hands them to us with connect_window().
# A "link" is eyes.py's PanelLink: anything with .send("show" / "hide" / "toggle").
# ---------------------------------------------------------------------------
_windows: dict = {}


def connect_window(name: str, link) -> None:
    """Tell the actions about a running window. None (window turned off) is ignored."""
    if link is not None:
        _windows[name] = link


def _send(window: str, word: str, said: str) -> str:
    """Send one word to a window, or say it isn't running."""
    link = _windows.get(window)
    if link is None:
        return f"The {window} window isn't running."
    link.send(word)
    return said


@action("show_music", "Bring the music window onto the screen.")
def show_music() -> str:
    return _send("music", "show", "Music window shown.")


@action("hide_music", "Put the music window away.")
def hide_music() -> str:
    return _send("music", "hide", "Music window hidden.")


@action("toggle_music", "Show the music window if it's hidden, hide it if it's showing.")
def toggle_music() -> str:
    return _send("music", "toggle", "Music window toggled.")


@action("put_away_sketch", "Put the sketch window away.")
def put_away_sketch() -> str:
    said = _send("sketch", "hide", "Sketch window put away.")
    if "sketch" in _windows:
        _windows["sketch"].frame = None      # it's gone, so nothing is "under the cursor" any more
    return said


# ---------------------------------------------------------------------------
# The wheel (wheel.py): FIVES's control room. Every window comes out of it and goes back into it.
# open_window / hide_window take any window from wheel_logic.WINDOWS, so a wedge click, an Option+number
# key, Rex, or a gesture all land in the same place. (The input is called `window` because run() already
# uses `name` for the action's name.)
# ---------------------------------------------------------------------------
@action("open_wheel", "Open the wheel: the round menu of every FIVES window.")
def open_wheel() -> str:
    return _send("wheel", "show", "Wheel opened.")


@action("close_wheel", "Close the wheel without opening anything.")
def close_wheel() -> str:
    return _send("wheel", "hide", "Wheel closed.")


def _window_name(name) -> str | None:
    """The window's proper name ("Music " -> "music"), or None if FIVES has no such window."""
    cleaned = str(name).strip().lower()
    return cleaned if cleaned in wheel_logic.WINDOWS else None


@action("open_window", "Bring one FIVES window into view.", {"window": "which window, e.g. music or settings"})
def open_window(window: str) -> str:
    name = _window_name(window)
    if name is None:
        return f"FIVES has no window called '{window}'."
    return _send(name, "show", f"{name.capitalize()} window opened.")


@action("hide_window", "Put one FIVES window away.", {"window": "which window, e.g. music or settings"})
def hide_window(window: str) -> str:
    name = _window_name(window)
    if name is None:
        return f"FIVES has no window called '{window}'."
    if name == "sketch":
        return put_away_sketch()          # the sketch window also has to forget where it was
    return _send(name, "hide", f"{name.capitalize()} window put away.")


# ---------------------------------------------------------------------------
# Music. The real code is Rex's music tool (music_tools.py), so nothing is built twice:
# Rex calls music_controls("skip"), a key or gesture calls run("skip"). Same code underneath.
# ---------------------------------------------------------------------------
MUSIC_CONTROLS = {                       # must match music_tools.CONTROLS (a test checks)
    "pause": "Pause the song that's playing.",
    "resume": "Keep playing the paused song.",
    "skip": "Skip to the next song.",
    "previous": "Go back to the song before this one.",
    "restart": "Start this song over from the beginning.",
}


def _music_control(word: str) -> Callable[[], str]:
    """Make the action for one control word. (A function that builds functions, so we don't write five copies.)"""
    def control() -> str:
        import music_tools      # imported here, not at the top, so eyes.py doesn't load Spotify/AppKit until needed
        return music_tools.music_controls(word)
    return control


for _word, _description in MUSIC_CONTROLS.items():
    action(_word, _description)(_music_control(_word))


@action("now_playing", "Say what song is playing right now.")
def now_playing() -> str:
    import music_tools
    return music_tools.now_playing()


if __name__ == "__main__":
    for item in ACTIONS.values():
        print(f"{item.name:16} {item.description}")
