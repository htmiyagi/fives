"""
settings.py - the everyday choices you make in the FIVES window's SETTINGS tab, remembered between runs.

They are saved in settings.json, next to this file. That file is YOURS: it is never uploaded to GitHub, and
UPDATE keeps it. (config.py is still where the hand-tracking numbers live. This is for simple choices that
anyone should be able to change with a click.)

    import settings
    settings.get("music_app")            ->  "Spotify"
    settings.put("music_app", "Apple Music")

Adding a setting: add one line to DEFAULTS (and to CHOICES if it's a pick-one). hub.py's SETTINGS tab lists
its rows in ROWS over there.
"""

import json
from pathlib import Path

import wheel_logic

FILE = Path(__file__).resolve().parent / "settings.json"

DEFAULTS = {
    "music_app": "Spotify",      # which app "play music" means
    "play_order": "Shuffle",     # what "play my playlist" does when you don't say shuffle or in order
    "ask_first": True,           # show me before anything is sent or deleted
    "speak_replies": False,      # read answers out loud
    "now_playing_popup": True,   # the little "PLAYING ..." note in the top-right corner (indicator.py)
    "wheel_order": list(wheel_logic.DEFAULT_ORDER),   # the wheel's wedges, clockwise from the top
}
CHOICES = {
    "music_app": ["Spotify", "Apple Music"],
    "play_order": ["Shuffle", "In order", "As is"],     # "As is" = keep whatever Spotify was doing
}

_cache = None
_cache_time = None     # when settings.json was last changed, as of our last read


def _file_time():
    """When settings.json was last saved (None if it doesn't exist yet)."""
    try:
        return FILE.stat().st_mtime
    except OSError:
        return None


def load() -> dict:
    """Everything, with defaults filled in for anything not chosen yet (or if the file got damaged).

    Re-reads the file whenever it changed, because the FIVES window and the chat are separate programs:
    flip a setting in the window, and the chat sees it on its very next request."""
    global _cache, _cache_time
    changed = _file_time()
    if _cache is None or changed != _cache_time:
        _cache_time = changed
        try:
            saved = json.loads(FILE.read_text())
        except (OSError, ValueError):
            saved = {}
        _cache = {key: saved.get(key, default) for key, default in DEFAULTS.items()}
        for key, allowed in CHOICES.items():             # a choice that no longer exists falls back to the default
            if _cache[key] not in allowed:
                _cache[key] = DEFAULTS[key]
    return _cache


def get(key):
    return load()[key]


def put(key, value) -> None:
    """Change one setting and save right away."""
    if key not in DEFAULTS:
        raise KeyError(key)
    load()[key] = value
    try:
        FILE.write_text(json.dumps(_cache, indent=2) + "\n")
    except OSError as err:
        print("settings: couldn't save:", err)
