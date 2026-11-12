"""
Tests for passcode.py and confirm_logic.py (the confirm box without its window).

Run them:   .venv/bin/python -m unittest test_confirm -v

The passcode file is pointed at a throwaway folder, so your real passcode.json is never touched.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import passcode
from confirm_logic import Confirm


class TempPasscodeFile(unittest.TestCase):
    """Base class: a throwaway passcode file, and a fast hash so tests don't take seconds."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, value in (("FILE", Path(folder.name) / "passcode.json"), ("ITERATIONS", 1000)):
            patcher = mock.patch.object(passcode, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class PasscodeTests(TempPasscodeFile):
    def test_right_and_wrong_passcodes(self):
        passcode.set_passcode("4417")
        self.assertTrue(passcode.check_passcode("4417"))
        self.assertFalse(passcode.check_passcode("4418"))

    def test_the_passcode_itself_is_never_saved(self):
        passcode.set_passcode("4417")
        saved = passcode.FILE.read_text()
        self.assertNotIn("4417", saved)
        self.assertEqual(set(json.loads(saved)), {"salt", "hash", "iterations"})

    def test_same_passcode_gets_a_different_hash_each_time(self):    # that's the salt doing its job
        passcode.set_passcode("4417")
        first = json.loads(passcode.FILE.read_text())["hash"]
        passcode.set_passcode("4417")
        self.assertNotEqual(first, json.loads(passcode.FILE.read_text())["hash"])

    def test_no_passcode_or_a_damaged_file_never_says_yes(self):
        self.assertFalse(passcode.has_passcode())
        self.assertFalse(passcode.check_passcode("anything"))
        passcode.FILE.write_text("not json")
        self.assertFalse(passcode.check_passcode("anything"))

    def test_too_short_is_refused(self):
        with self.assertRaises(ValueError):
            passcode.set_passcode("12")


def typed(box, text):
    """Type a word into the box and press Enter."""
    for char in text:
        box.type_char(char)
    box.submit()


class ConfirmTests(TempPasscodeFile):
    def test_right_passcode_confirms(self):
        passcode.set_passcode("4417")
        box = Confirm("Delete 'Gym'?")
        typed(box, "4417")
        self.assertIs(box.result, True)

    def test_three_wrong_tries_cancels(self):
        passcode.set_passcode("4417")
        box = Confirm("Delete 'Gym'?")
        typed(box, "1111")
        self.assertEqual(box.message, "WRONG PASSCODE. 2 TRIES LEFT")
        typed(box, "2222")
        self.assertEqual(box.message, "WRONG PASSCODE. 1 TRY LEFT")
        typed(box, "3333")
        self.assertIs(box.result, False)
        self.assertEqual(box.message, "TOO MANY WRONG TRIES. LOCKED FOR 1:00")
        typed(box, "4417")                                          # too late: it's already cancelled
        self.assertIs(box.result, False)

    def test_a_new_box_does_not_give_fresh_tries(self):           # the hole Hoyu found
        passcode.set_passcode("4417")
        typed(Confirm("?"), "1111")
        typed(Confirm("?"), "2222")
        self.assertEqual(Confirm("?").tries_left, 1)

    def test_a_locked_box_shows_the_countdown_and_takes_no_passcode(self):
        passcode.set_passcode("4417")
        for guess in ("1111", "2222", "3333"):
            passcode.attempt(guess)
        box = Confirm("?")
        self.assertEqual(box.mode, "locked")
        self.assertEqual(box.message, "LOCKED. TRY AGAIN IN 1:00")
        typed(box, "4417")
        self.assertIsNone(box.result)                               # ignored, not confirmed

    def test_a_locked_box_unlocks_when_the_time_runs_out(self):
        passcode.set_passcode("4417")
        for guess in ("1111", "2222", "3333"):
            passcode.attempt(guess)
        box = Confirm("?")
        with mock.patch("passcode._now", lambda: passcode.time.time() + 61):
            box.refresh()
            self.assertEqual(box.mode, "enter")
            typed(box, "4417")
        self.assertIs(box.result, True)


    def test_dots_are_cleared_after_each_try(self):
        passcode.set_passcode("4417")
        box = Confirm("?")
        typed(box, "1111")
        self.assertEqual(box.typed, "")

    def test_first_time_makes_a_passcode_after_typing_it_twice(self):
        box = Confirm("Delete 'Gym'?")
        self.assertEqual(box.mode, "create")
        typed(box, "4417")
        self.assertEqual(box.mode, "repeat")
        typed(box, "4417")
        self.assertIs(box.result, True)
        self.assertTrue(passcode.check_passcode("4417"))

    def test_mismatched_repeat_starts_over_and_saves_nothing(self):
        box = Confirm("?")
        typed(box, "4417")
        typed(box, "9999")
        self.assertEqual((box.mode, box.result), ("create", None))
        self.assertFalse(passcode.has_passcode())

    def test_too_short_new_passcode_is_refused(self):
        box = Confirm("?")
        typed(box, "12")
        self.assertEqual(box.mode, "create")
        self.assertIn("TOO SHORT", box.message)

    def test_cancel(self):
        box = Confirm("?")
        box.cancel()
        self.assertIs(box.result, False)


class LockoutTests(TempPasscodeFile):
    def setUp(self):
        super().setUp()
        self.clock = 1_000_000.0                                    # a pretend clock we can move by hand
        patcher = mock.patch("passcode._now", lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        passcode.set_passcode("4417")

    def miss_three(self):
        for guess in ("1111", "2222", "3333"):
            self.assertFalse(passcode.attempt(guess))

    def test_locks_get_longer_then_stay_at_one_hour(self):
        lengths = []
        for _ in range(6):
            self.miss_three()
            lengths.append(passcode.locked_for())
            self.clock += 60 * 60                                   # wait out the lock
        self.assertEqual(lengths, [60, 300, 900, 3600, 3600, 3600])

    def test_even_the_right_passcode_is_refused_while_locked(self):
        self.miss_three()
        self.assertFalse(passcode.attempt("4417"))
        self.clock += 61
        self.assertTrue(passcode.attempt("4417"))

    def test_the_right_passcode_resets_the_streak(self):
        self.assertFalse(passcode.attempt("1111"))
        self.assertFalse(passcode.attempt("2222"))
        self.assertTrue(passcode.attempt("4417"))
        self.assertEqual(passcode.tries_left(), 3)
        self.miss_three()
        self.assertEqual(passcode.locked_for(), 60)                 # back to the first, shortest lock

    def test_setting_the_clock_back_does_not_unlock_or_stretch_it(self):
        self.miss_three()
        self.clock -= 24 * 60 * 60                                  # someone sets the Mac a day back
        self.assertEqual(passcode.locked_for(), 60)                 # still locked, and never longer than 1:00

    def test_the_saved_file_still_holds_no_passcode(self):
        self.miss_three()
        self.assertNotIn("4417", passcode.FILE.read_text())

if __name__ == "__main__":
    unittest.main()
