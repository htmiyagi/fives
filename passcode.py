"""
passcode.py - the passcode that guards risky actions (like deleting a playlist), stored the way good websites do.

We never save the passcode itself. We save a HASH of it: a one-way scramble. The same passcode always scrambles
to the same hash, but you can't unscramble a hash back into the passcode. To check a guess, we scramble the guess
and compare. (Like checking a fingerprint without keeping the finger.)

Two extra website tricks:
    salt        random bytes mixed in before scrambling, different on every Mac. So two people who both pick
                "1234" get different hashes, and a list of pre-scrambled common passcodes is useless.
    slow hash   PBKDF2 scrambles ITERATIONS times in a row. One check takes a moment; guessing millions takes forever.

Saved in passcode.json next to this file (gitignored, readable only by you). Its own file, NOT settings.json:
hub.py keeps a copy of settings in memory and writes the whole thing back, which would erase a passcode
saved by the confirm box (a separate program).

Wrong tries are remembered here too, so closing the box and opening a new one doesn't give fresh guesses.
Every TRIES_PER_LOCK wrong tries in a row locks it, longer each time (like an iPhone): 1 min, 5 min, 15 min,
then 1 hour from there on. The right passcode resets the streak.

Only confirm_box.py should call these. The passcode must never go anywhere near Rex (the model).
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

FILE = Path(__file__).resolve().parent / "passcode.json"
ITERATIONS = 600_000            # how many times PBKDF2 scrambles (the 2023+ recommendation for SHA-256)
MIN_LENGTH = 4                  # shortest passcode we accept
SALT_BYTES = 16
TRIES_PER_LOCK = 3              # wrong tries in a row before it locks
LOCKOUTS = [60, 5 * 60, 15 * 60, 60 * 60]      # seconds: 1st lock, 2nd, 3rd, then the last one forever


def _now() -> float:
    return time.time()          # its own function so tests can pretend time has passed


def _scramble(code: str, salt: bytes, iterations: int) -> bytes:
    """The slow, salted, one-way hash of a passcode."""
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, iterations)


def _load() -> dict:
    try:
        saved = json.loads(FILE.read_text())
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(saved: dict) -> None:
    FILE.write_text(json.dumps(saved, indent=2) + "\n")
    os.chmod(FILE, 0o600)                               # only you can read it


def has_passcode() -> bool:
    """Has a passcode been made on this Mac yet?"""
    saved = _load()
    return bool(saved.get("hash") and saved.get("salt"))


def set_passcode(code: str) -> None:
    """Save a new passcode (as a salted hash). Raises ValueError if it's too short."""
    if len(code) < MIN_LENGTH:
        raise ValueError(f"A passcode needs at least {MIN_LENGTH} characters.")
    salt = secrets.token_bytes(SALT_BYTES)
    _save({"salt": salt.hex(), "hash": _scramble(code, salt, ITERATIONS).hex(), "iterations": ITERATIONS})


def check_passcode(code: str) -> bool:
    """Is this the right passcode? False if there's no passcode or the file is damaged (never crashes)."""
    saved = _load()
    try:
        salt = bytes.fromhex(saved["salt"])
        expected = bytes.fromhex(saved["hash"])
        iterations = int(saved.get("iterations", ITERATIONS))
    except (KeyError, ValueError, TypeError):
        return False
    # compare_digest takes the same time whether the first byte or the last byte differs, so timing leaks nothing
    return hmac.compare_digest(_scramble(code, salt, iterations), expected)


# ---- the lockout -------------------------------------------------------------------------------------
def locked_for() -> float:
    """Seconds until a passcode can be tried again (0 = not locked).

    If the Mac's clock gets set BACK, "now" is before the lock started, and the wait would look huge or
    negative. So the wait is capped at that lock's full length: changing the clock never unlocks it early."""
    saved = _load()
    length = float(saved.get("lock_seconds", 0) or 0)
    remaining = float(saved.get("locked_at", 0) or 0) + length - _now()
    return max(0.0, min(remaining, length))


def tries_left() -> int:
    """Wrong tries left before the next lock (counts across boxes, not just this one)."""
    return TRIES_PER_LOCK - int(_load().get("wrong", 0) or 0) % TRIES_PER_LOCK


def attempt(code: str) -> bool:
    """Try a passcode, keeping score. Never says yes while locked, even to the right passcode."""
    if locked_for() > 0:
        return False
    saved = _load()
    if check_passcode(code):
        _save({key: saved[key] for key in ("salt", "hash", "iterations") if key in saved})   # streak back to 0
        return True
    wrong = int(saved.get("wrong", 0) or 0) + 1
    update = {"wrong": wrong}
    if wrong % TRIES_PER_LOCK == 0:                     # every 3rd wrong try in a row: lock, longer each time
        which = min(wrong // TRIES_PER_LOCK - 1, len(LOCKOUTS) - 1)
        update.update(locked_at=_now(), lock_seconds=LOCKOUTS[which])
    _save({**saved, **update})
    return False
