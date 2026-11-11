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

FILE = Path(__file__).resolve().parent / "settings.json"

DEFAULTS = {
    "music_app": "Spotify",      # which app "play music" means
    "ask_first": True,           # show me before anything is sent or deleted
    "speak_replies": False,      # read answers out loud
}
CHOICES = {
    "music_app": ["Spotify", "Apple Music"],
}

_cache = None


def load() -> dict:
    """Everything, with defaults filled in for anything not chosen yet (or if the file got damaged)."""
    global _cache
    if _cache is None:
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
