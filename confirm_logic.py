"""
confirm_logic.py - what the confirm box DOES, with no drawing code (confirm_box.py draws it). Testable on its own,
like panel_logic.py is for panel.py.

The box has three modes:
    enter    a passcode exists: type it. 3 wrong tries = this action is cancelled.
    create   no passcode yet: make one...
    repeat   ...and type it again, so a typo doesn't lock you out.

Known gap (on purpose, for now): the FIRST time, whoever is at the Mac gets to create the passcode.

It only ever ends with result = True (confirmed) or False (cancelled). The passcode itself never leaves this
object, so confirm_box.py can report a plain "yes" / "no" and nothing else.
"""

import passcode

MAX_TRIES = 3


class Confirm:
    def __init__(self, question: str, store=passcode):
        self.question = question
        self.store = store                           # passcode.py (swapped for a fake in tests)
        self.mode = "enter" if store.has_passcode() else "create"
        self.typed = ""
        self.first = ""                              # create mode: the passcode typed the first time
        self.tries_left = MAX_TRIES
        self.result = None                           # None = still asking, True = confirmed, False = cancelled
        self.message = self._hint()

    def _hint(self) -> str:
        return {"enter": "ENTER YOUR PASSCODE",
                "create": f"NO PASSCODE YET. MAKE ONE ({self.store.MIN_LENGTH}+ CHARACTERS)",
                "repeat": "TYPE IT AGAIN"}[self.mode]

    def type_char(self, char: str) -> None:
        if self.result is None and char.isprintable() and char != " ":
            self.typed += char

    def backspace(self) -> None:
        self.typed = self.typed[:-1]

    def cancel(self) -> None:
        if self.result is None:
            self.result, self.message = False, "CANCELLED"

    def submit(self) -> None:
        """Enter / CONFIRM was pressed."""
        if self.result is not None or not self.typed:
            return
        typed, self.typed = self.typed, ""           # clear the dots straight away, whatever happens
        if self.mode == "enter":
            self._check(typed)
        elif self.mode == "create":
            self._create(typed)
        else:
            self._repeat(typed)

    def _check(self, typed: str) -> None:
        if self.store.check_passcode(typed):
            self.result, self.message = True, "CONFIRMED"
            return
        self.tries_left -= 1
        if self.tries_left <= 0:
            self.result, self.message = False, "TOO MANY WRONG TRIES. CANCELLED"
        else:
            self.message = f"WRONG PASSCODE. {self.tries_left} {'TRY' if self.tries_left == 1 else 'TRIES'} LEFT"

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
