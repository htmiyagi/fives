"""
confirm_logic.py - what the confirm box DOES, with no drawing code (confirm_box.py draws it). Testable on its own,
like panel_logic.py is for panel.py.

The box has four modes:
    enter    a passcode exists: type it. Every 3rd wrong try in a row locks it (passcode.py keeps score, so a
             new box doesn't give fresh tries) and cancels this action.
    locked   too many wrong tries lately: shows a countdown and takes no passcode until it runs out.
    create   no passcode yet: make one...
    repeat   ...and type it again, so a typo doesn't lock you out.

Known gap (on purpose, for now): the FIRST time, whoever is at the Mac gets to create the passcode.

It only ever ends with result = True (confirmed) or False (cancelled). The passcode itself never leaves this
object, so confirm_box.py can report a plain "yes" / "no" and nothing else.
"""

import passcode


def clock(seconds: float) -> str:
    """75 -> '1:15'  (rounded up, so it never shows 0:00 while still locked)"""
    whole = int(-(-seconds // 1))
    return f"{whole // 60}:{whole % 60:02d}"


class Confirm:
    def __init__(self, question: str, store=passcode):
        self.question = question
        self.store = store                           # passcode.py (swapped for a fake in tests)
        if not store.has_passcode():
            self.mode = "create"
        else:
            self.mode = "locked" if store.locked_for() > 0 else "enter"
        self.typed = ""
        self.first = ""                              # create mode: the passcode typed the first time
        self.result = None                           # None = still asking, True = confirmed, False = cancelled
        self.message = self._hint()

    @property
    def tries_left(self) -> int:
        """Wrong tries left before the next lock (a property: reads like a variable, but asks passcode.py)."""
        return self.store.tries_left()

    def _hint(self) -> str:
        if self.mode == "locked":
            return f"LOCKED. TRY AGAIN IN {clock(self.store.locked_for())}"
        return {"enter": "ENTER YOUR PASSCODE",
                "create": f"NO PASSCODE YET. MAKE ONE ({self.store.MIN_LENGTH}+ CHARACTERS)",
                "repeat": "TYPE IT AGAIN"}[self.mode]

    def refresh(self) -> None:
        """Called many times a second by the box: tick the countdown, and unlock when it runs out."""
        if self.result is not None or self.mode != "locked":
            return
        if self.store.locked_for() <= 0:
            self.mode = "enter"
        self.message = self._hint()

    def type_char(self, char: str) -> None:
        if self.result is None and self.mode != "locked" and char.isprintable() and char != " ":
            self.typed += char

    def backspace(self) -> None:
        self.typed = self.typed[:-1]

    def cancel(self) -> None:
        if self.result is None:
            self.result, self.message = False, "CANCELLED"

    def submit(self) -> None:
        """Enter / CONFIRM was pressed."""
        if self.result is not None or self.mode == "locked" or not self.typed:
            return
        typed, self.typed = self.typed, ""           # clear the dots straight away, whatever happens
        if self.mode == "enter":
            self._check(typed)
        elif self.mode == "create":
            self._create(typed)
        else:
            self._repeat(typed)

    def _check(self, typed: str) -> None:
        if self.store.attempt(typed):                # attempt() also keeps score of wrong tries
            self.result, self.message = True, "CONFIRMED"
            return
        lock = self.store.locked_for()
        if lock > 0:                                 # that was the 3rd wrong try in a row: locked, and cancelled
            self.result, self.message = False, f"TOO MANY WRONG TRIES. LOCKED FOR {clock(lock)}"
        else:
            left = self.tries_left
            self.message = f"WRONG PASSCODE. {left} {'TRY' if left == 1 else 'TRIES'} LEFT"

    def _create(self, typed: str) -> None:
        if len(typed) < self.store.MIN_LENGTH:
            self.message = f"TOO SHORT. AT LEAST {self.store.MIN_LENGTH} CHARACTERS"
            return
        self.first, self.mode = typed, "repeat"
        self.message = self._hint()

    def _repeat(self, typed: str) -> None:
        if typed != self.first:
            self.first, self.mode = "", "create"
            self.message = "DIDN'T MATCH. MAKE ONE AGAIN"
            return
        self.store.set_passcode(typed)
        self.first = ""
        self.result, self.message = True, "PASSCODE SAVED. CONFIRMED"
