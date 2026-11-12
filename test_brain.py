"""
Tests for brain.py's instant shortcuts ("skip", "pause", ...), with no model and no Spotify.

Run them:   .venv/bin/python -m unittest test_brain -v

`mock.patch` swaps in fakes while a test runs: run_tool pretends to be music_controls, and ollama.chat
blows up if it's ever called, so a test fails loudly if a shortcut accidentally reaches the model.
"""

import unittest
from unittest import mock

import brain


class ShortcutWords(unittest.TestCase):
    def test_plain_commands_are_shortcuts(self):
        self.assertEqual(brain.shortcut_action("skip"), "skip")
        self.assertEqual(brain.shortcut_action("next"), "skip")
        self.assertEqual(brain.shortcut_action("pause"), "pause")
        self.assertEqual(brain.shortcut_action("play"), "resume")
        self.assertEqual(brain.shortcut_action("back"), "previous")

    def test_case_punctuation_and_please_are_ignored(self):
        self.assertEqual(brain.shortcut_action("Skip!"), "skip")
        self.assertEqual(brain.shortcut_action("  next song, please "), "skip")
        self.assertEqual(brain.shortcut_action("Rex, pause."), "pause")

    def test_phrases_rex_faked_in_testing_are_shortcuts(self):   # these reached the model and it made up a reply
        self.assertEqual(brain.shortcut_action("skip it"), "skip")
        self.assertEqual(brain.shortcut_action("rewind to start!! :D"), "restart")

    def test_longer_requests_still_go_to_the_model(self):
        self.assertIsNone(brain.shortcut_action("skip this and play Radiohead"))
        self.assertIsNone(brain.shortcut_action("play Get Lucky"))
        self.assertIsNone(brain.shortcut_action("what's playing?"))
        self.assertIsNone(brain.shortcut_action(""))


class ShortcutsSkipTheModel(unittest.TestCase):
    def setUp(self):
        self.ran = []                                      # every (tool name, args) the brain ran

        def fake_run_tool(name, args):
            self.ran.append((name, args))
            return "Skipped. Now playing Get Lucky by Daft Punk."

        for target, fake in (("brain.run_tool", fake_run_tool),
                             ("brain.ollama.chat", mock.Mock(side_effect=AssertionError("model was called")))):
            patcher = mock.patch(target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_skip_runs_music_controls_without_the_model(self):
        reply = brain.think([], "skip")
        self.assertEqual(self.ran, [("music_controls", {"action": "skip"})])
        self.assertEqual(reply, "Skipped. Now playing Get Lucky by Daft Punk.")

    def test_shortcut_is_remembered_as_a_real_tool_call(self):   # else Rex learns to fake it
        messages = []
        brain.think(messages, "skip")
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "music_controls")   # the tool call
        self.assertIn("Get Lucky", messages[2]["content"])                                     # what it said
        self.assertIn("Get Lucky", messages[-1]["content"])                                    # the reply

    def test_shortcut_tells_the_screen_which_tool_ran(self):
        seen = []
        brain.think([], "next", on_tool=lambda name, args, result: seen.append(name))
        self.assertEqual(seen, ["music_controls"])


if __name__ == "__main__":
    unittest.main()
