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

Only confirm_box.py should call these. The passcode must never go anywhere near Rex (the model).
"""

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

FILE = Path(__file__).resolve().parent / "passcode.json"
ITERATIONS = 600_000            # how many times PBKDF2 scrambles (the 2023+ recommendation for SHA-256)
MIN_LENGTH = 4                  # shortest passcode we accept
SALT_BYTES = 16


def _scramble(code: str, salt: bytes, iterations: int) -> bytes:
    """The slow, salted, one-way hash of a passcode."""
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, iterations)


def _load() -> dict:
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def has_passcode() -> bool:
    """Has a passcode been made on this Mac yet?"""
    saved = _load()
    return bool(saved.get("hash") and saved.get("salt"))


def set_passcode(code: str) -> None:
    """Save a new passcode (as a salted hash). Raises ValueError if it's too short."""
    if len(code) < MIN_LENGTH:
        raise ValueError(f"A passcode needs at least {MIN_LENGTH} characters.")
    salt = secrets.token_bytes(SALT_BYTES)
    saved = {"salt": salt.hex(), "hash": _scramble(code, salt, ITERATIONS).hex(), "iterations": ITERATIONS}
    FILE.write_text(json.dumps(saved, indent=2) + "\n")
    os.chmod(FILE, 0o600)                               # only you can read it


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
