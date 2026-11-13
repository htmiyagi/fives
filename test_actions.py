"""
Tests for actions.py: the registry, the gesture table, and the window/music actions.
No real windows open and no music plays.

Run them:   .venv/bin/python -m unittest test_actions -v

A FakeWindow stands in for eyes.py's PanelLink: it just remembers the words it was sent.
"""

import unittest
from unittest import mock

import actions
import music_tools


class FakeWindow:
    """Pretends to be a FIVES window. send() writes the word down instead of moving anything."""
    def __init__(self):
        self.sent = []
        self.frame = (0, 0, 100, 100)

    def send(self, word):
        self.sent.append(word)


class Registry(unittest.TestCase):
    def test_every_action_has_a_name_description_and_function(self):
        for name, item in actions.ACTIONS.items():
            self.assertEqual(item.name, name)
            self.assertTrue(item.description.strip(), f"{name} has no description")
            self.assertTrue(callable(item.run), f"{name} can't be run")

    def test_the_existing_features_are_registered(self):
        expected = {"show_music", "hide_music", "toggle_music", "put_away_sketch",
                    "pause", "resume", "skip", "previous", "restart", "now_playing"}
        self.assertTrue(expected <= set(actions.ACTIONS))

    def test_unknown_action_returns_a_sentence(self):
        self.assertEqual(actions.run("fly_to_moon"), "FIVES has no action called 'fly_to_moon'.")

    def test_a_crashing_action_returns_the_error_instead(self):
        def broken():
            raise RuntimeError("boom")
        with mock.patch.dict(actions.ACTIONS, {"broken": actions.Action("broken", "Always fails.", broken)}):
            self.assertEqual(actions.run("broken"), "Something went wrong in broken: boom")

    def test_two_actions_with_the_same_name_fail_loudly(self):
        with self.assertRaises(ValueError):
            actions.action("skip", "A second skip.")(lambda: "nope")

    def test_music_actions_match_rexs_music_tool(self):
        # If someone adds a control to music_tools, this reminds them to add the action too.
        self.assertEqual(set(actions.MUSIC_CONTROLS), set(music_tools.CONTROLS))


class GestureMap(unittest.TestCase):
    def test_every_gesture_points_at_a_real_action(self):
        for gesture, name in actions.GESTURES.items():
            self.assertIn(name, actions.ACTIONS, f"{gesture} -> {name}, but there's no such action")

    def test_open_palm_flick_opens_and_closes_the_wheel(self):
        self.assertEqual(actions.action_for("flick_left"), "open_wheel")
        self.assertEqual(actions.action_for("flick_right"), "close_wheel")

    def test_flick_on_the_sketch_window_puts_it_away(self):
        self.assertEqual(actions.action_for("flick_right", "sketch"), "put_away_sketch")
        self.assertEqual(actions.action_for("flick_left", "sketch"), "put_away_sketch")

    def test_window_with_no_special_line_falls_back_to_plain_gesture(self):
        self.assertEqual(actions.action_for("flick_right", "calendar"), "close_wheel")

    def test_unknown_gesture_means_nothing(self):
        self.assertIsNone(actions.action_for("thumbs_up"))


class WindowActions(unittest.TestCase):
    def setUp(self):
        self.music, self.sketch = FakeWindow(), FakeWindow()
        patcher = mock.patch.dict(actions._windows, {"music": self.music, "sketch": self.sketch}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_hide_show_toggle_send_the_same_words_as_before(self):
        self.assertEqual(actions.run("hide_music"), "Music window hidden.")
        actions.run("show_music")
        actions.run("toggle_music")
        self.assertEqual(self.music.sent, ["hide", "show", "toggle"])

    def test_put_away_sketch_hides_it_and_forgets_where_it_was(self):
        self.assertEqual(actions.run("put_away_sketch"), "Sketch window put away.")
        self.assertEqual(self.sketch.sent, ["hide"])
        self.assertIsNone(self.sketch.frame)

    def test_window_that_isnt_running_says_so(self):
        actions._windows.clear()
        self.assertEqual(actions.run("hide_music"), "The music window isn't running.")
        self.assertEqual(actions.run("put_away_sketch"), "The sketch window isn't running.")

    def test_the_fives_window_can_be_put_away_and_brought_back(self):
        hub = FakeWindow()
        actions._windows[actions.HUB] = hub
        self.assertIn("FIVES window put away", actions.run("hide_window", window="fives"))
        actions.run("open_window", window="FIVES")      # the undo flick
        self.assertEqual(hub.sent, ["hide", "show"])

    def test_connect_window_ignores_a_window_thats_turned_off(self):
        actions._windows.clear()
        actions.connect_window("music", None)
        self.assertNotIn("music", actions._windows)


class MusicActions(unittest.TestCase):
    def test_each_control_calls_rexs_music_tool(self):
        for word in actions.MUSIC_CONTROLS:
            with mock.patch("music_tools.music_controls", return_value="ok") as rex_tool:
                self.assertEqual(actions.run(word), "ok")
                rex_tool.assert_called_once_with(word)

    def test_now_playing_calls_rexs_now_playing(self):
        with mock.patch("music_tools.now_playing", return_value="Playing X by Y."):
            self.assertEqual(actions.run("now_playing"), "Playing X by Y.")


if __name__ == "__main__":
    unittest.main()
