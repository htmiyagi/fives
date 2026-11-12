"""
tools.py - FIVES's hands.

Each tool is an ordinary Python function. The @tool line above it adds it to
the TOOLS list, which is the menu the brain is allowed to choose from.

The brain never sees your code. It only sees:
  - the function's name
  - its type hints (name: str, level: int)
  - its docstring (the text in triple quotes)
So write the docstring like you're explaining the tool to a new assistant.
"""

import datetime
import subprocess

TOOLS = []


def tool(fn):
    """Register a function as a tool FIVES can use."""
    TOOLS.append(fn)
    return fn


def _run(command: list) -> subprocess.CompletedProcess:
    """Run a Mac command and capture what it prints. (Not a tool: no @tool.)"""
    return subprocess.run(command, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------

@tool
def open_app(name: str) -> str:
    """Open a Mac application by name.

    Args:
        name: The app's name, for example "Safari", "Spotify", or "Notes".
    """
    result = _run(["open", "-a", name])
    if result.returncode == 0:
        return f"Opened {name}."
    return f"Couldn't open {name}: {result.stderr.strip()}"


# Quitting these would quit FIVES itself (it runs inside them).
APPS_FIVES_RUNS_IN = {"terminal", "python", "fives"}
QUIT_WAIT_SECONDS = 5      # how long to wait before giving up on an app stuck on a "save changes?" box

# AppleScript that politely quits an app (like Cmd+Q). The app's name arrives as `argv`, a separate
# argument, never pasted into this text, so a name with quotes in it can't sneak in its own commands.
QUIT_SCRIPT = [
    "on run argv",
    "set appName to item 1 of argv",
    'if application appName is not running then return "not running"',
    f"with timeout of {QUIT_WAIT_SECONDS} seconds",
    "tell application appName to quit",
    "end timeout",
    'return "quit"',
    "end run",
]


@tool
def close_app(name: str) -> str:
    """Quit a Mac application by name, like pressing Cmd+Q. If it has unsaved work, it asks first.

    Args:
        name: The app's name, for example "Safari", "Notes", or "OBS".
    """
    if name.strip().lower() in APPS_FIVES_RUNS_IN:
        return f"I won't close {name}: FIVES is running in it."
    command = ["osascript"] + [part for line in QUIT_SCRIPT for part in ("-e", line)] + [name]
    result = _run(command)
    if result.returncode == 0:
        return f"{name} isn't open." if result.stdout.strip() == "not running" else f"Closed {name}."
    if "-1712" in result.stderr:   # AppleScript's "timed out" code: a save box is waiting on you
        return f"Asked {name} to quit. It's waiting for you to save or cancel."
    if "-128" in result.stderr:    # "user canceled": you clicked Cancel in the save box
        return f"{name} is still open: you chose to keep it."
    return f"Couldn't close {name}: {result.stderr.strip()}"


@tool
def open_url(url: str) -> str:
    """Open a website in the default browser.

    Args:
        url: The full address, for example "https://github.com".
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _run(["open", url])
    return f"Opened {url}."


@tool
def set_volume(level: int) -> str:
    """Set the Mac's output volume.

    Args:
        level: A whole number from 0 (silent) to 100 (max).
    """
    level = max(0, min(100, int(level)))
    _run(["osascript", "-e", f"set volume output volume {level}"])
    return f"Volume set to {level}."


@tool
def run_shortcut(name: str) -> str:
    """Run one of the user's macOS Shortcuts by its exact name.

    Args:
        name: The Shortcut's name as it appears in the Shortcuts app.
    """
    result = _run(["shortcuts", "run", name])
    if result.returncode == 0:
        return f"Ran shortcut '{name}'."
    return f"Shortcut failed: {result.stderr.strip()}"


@tool
def get_time() -> str:
    """Get the current date and time."""
    return datetime.datetime.now().strftime("It's %A, %B %d, %I:%M %p.")


@tool
def study_mode() -> str:
    """Set up the Mac for focused studying: opens Notes and Safari, lowers the volume."""
    steps = [open_app("Notes"), open_app("Safari"), set_volume(20)]
    return " ".join(steps)


# ---------------------------------------------------------------------------
# Music. The code lives in music_tools.py; this just puts it on the menu. (music_controls works without Premium.)
# actions.py's pause / skip / now_playing etc. call these same functions, so keys and gestures share Rex's code.
# ---------------------------------------------------------------------------
from music_tools import (add_to_playlist, delete_playlist, make_playlist, music_controls,  # noqa: E402
                         now_playing, play_music, queue_song)

for music_tool in (play_music, music_controls, queue_song, now_playing, make_playlist, add_to_playlist,
                   delete_playlist):
    tool(music_tool)
