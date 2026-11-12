"""
Tests for tools.py's close_app, with no real apps quit.

Run them:   .venv/bin/python -m unittest test_tools -v

`mock.patch` swaps tools._run for a fake, so we can pretend osascript said anything we like
and check what close_app would have run.
"""

import subprocess
import unittest
from unittest import mock

import tools


def osascript_said(stdout="", stderr="", returncode=0):
    """A fake result, shaped like what subprocess.run hands back."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class CloseApp(unittest.TestCase):
    def test_quits_a_running_app(self):
        with mock.patch("tools._run", return_value=osascript_said("quit\n")):
            self.assertEqual(tools.close_app("Notes"), "Closed Notes.")

    def test_app_that_isnt_open(self):
        with mock.patch("tools._run", return_value=osascript_said("not running\n")):
            self.assertEqual(tools.close_app("Notes"), "Notes isn't open.")

    def test_app_waiting_on_a_save_box(self):              # AppleScript timed out waiting for you
        with mock.patch("tools._run", return_value=osascript_said(stderr="AppleEvent timed out. (-1712)",
                                                                  returncode=1)):
            self.assertEqual(tools.close_app("TextEdit"),
                             "Asked TextEdit to quit. It's waiting for you to save or cancel.")

    def test_you_said_cancel_in_the_save_box(self):
        with mock.patch("tools._run", return_value=osascript_said(stderr="User canceled. (-128)", returncode=1)):
            self.assertEqual(tools.close_app("TextEdit"), "TextEdit is still open: you chose to keep it.")

    def test_other_errors_are_reported_not_raised(self):
        with mock.patch("tools._run", return_value=osascript_said(stderr="Not authorized. (-1743)", returncode=1)):
            self.assertTrue(tools.close_app("Mail").startswith("Couldn't close Mail:"))

    def test_the_name_is_passed_separately_not_pasted_into_the_script(self):   # so quotes can't inject code
        sneaky = 'Notes" to do shell script "say hi'
        with mock.patch("tools._run", return_value=osascript_said("not running\n")) as run:
            tools.close_app(sneaky)
        command = run.call_args.args[0]
        self.assertEqual(command[-1], sneaky)                                  # last argument, as data
        self.assertFalse(any(sneaky in part for part in command[:-1]))         # never inside the script

    def test_wont_quit_the_apps_fives_runs_in(self):
        with mock.patch("tools._run") as run:
            reply = tools.close_app("Terminal")
        run.assert_not_called()
        self.assertEqual(reply, "I won't close Terminal: FIVES is running in it.")

    def test_close_app_is_on_the_menu(self):
        self.assertIn(tools.close_app, tools.TOOLS)


if __name__ == "__main__":
    unittest.main()
