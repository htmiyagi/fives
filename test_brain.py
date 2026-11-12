"""
Tests for brain.py: instant shortcuts ("skip", "pause", ...) and the run-first loop, with no model and no Spotify.

Run them:   .venv/bin/python -m unittest test_brain -v

`mock.patch` swaps in fakes while a test runs: run_tool pretends to be music_controls, and ollama.chat
blows up if it's ever called, so a test fails loudly if a shortcut accidentally reaches the model.
"""

import unittest
from types import SimpleNamespace
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


def fake_model_reply(tool_name="", args=None, content=""):
    """What ollama.chat hands back: either a tool call (tool_name set) or plain words (content)."""
    calls = [SimpleNamespace(function=SimpleNamespace(name=tool_name, arguments=args or {}))] if tool_name else None
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls))


class ToolSentencesAreShownAsIs(unittest.TestCase):
    """Every tool already writes a correct sentence, so Rex shows it instead of rewording it
    (rewording is where he swapped song and artist names in testing, and it costs a model call)."""

    def setUp(self):
        self.model = mock.Mock()
        self.tool_sentences = {"play_music": "Playing nouvelle vague by wave to earth.",
                               "open_app": "Opened Safari.",
                               "make_playlist": "Made 'chill' with 3 songs."}
        for target, fake in (("brain.run_tool", lambda name, args: self.tool_sentences[name]),
                             ("brain.ollama.chat", self.model)):
            patcher = mock.patch(target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_play_music_reply_is_the_tool_sentence_word_for_word(self):
        self.model.side_effect = [fake_model_reply("play_music", {"what": "nouvelle vague"})]
        reply = brain.think([], "play nouvelle vague by wave to earth")
        self.assertEqual(reply, "Playing nouvelle vague by wave to earth.")
        self.assertEqual(self.model.call_count, 1)                 # no second "reword it" call

    def test_shown_sentence_is_remembered_as_the_reply(self):
        self.model.side_effect = [fake_model_reply("play_music", {"what": "nouvelle vague"})]
        messages = []
        brain.think(messages, "play nouvelle vague")
        self.assertEqual(messages[-1], {"role": "assistant", "content": "Playing nouvelle vague by wave to earth."})

    def test_non_music_tools_also_skip_the_reword(self):        # run-first: true for every tool now
        self.model.side_effect = [fake_model_reply("make_playlist", {"name": "chill", "songs": []})]
        reply = brain.think([], "make a chill playlist")
        self.assertEqual(reply, "Made 'chill' with 3 songs.")
        self.assertEqual(self.model.call_count, 1)

    def test_a_possible_step_two_gets_one_more_round(self):     # "...and open Safari" must not be dropped
        self.model.side_effect = [fake_model_reply("play_music", {"what": "nouvelle vague"}),
                                  fake_model_reply("open_app", {"name": "Safari"})]
        reply = brain.think([], "play nouvelle vague and open safari")
        self.assertEqual(reply, "Playing nouvelle vague by wave to earth. Opened Safari.")   # both rounds' words
        self.assertEqual(self.model.call_count, 2)                 # one extra round, not a third reword

    def test_extra_round_with_nothing_left_uses_rexs_words(self):   # e.g. "Simon and Garfunkel"
        self.model.side_effect = [fake_model_reply("play_music", {"what": "the boxer"}),
                                  fake_model_reply(content="Playing The Boxer by Simon & Garfunkel.")]
        reply = brain.think([], "play the boxer by simon and garfunkel")
        self.assertEqual(reply, "Playing The Boxer by Simon & Garfunkel.")
        self.assertEqual(self.model.call_count, 2)


class WhenToGoAnotherRound(unittest.TestCase):
    def test_failed_sounding_sentences_are_spotted(self):
        self.assertTrue(brain.sounds_failed("Couldn't find a song called 'xyz' on Spotify."))
        self.assertTrue(brain.sounds_failed("Something went wrong with Spotify: timeout"))
        self.assertTrue(brain.sounds_failed("There is no tool called fly."))
        self.assertFalse(brain.sounds_failed("Playing Get Lucky by Daft Punk."))
        self.assertFalse(brain.sounds_failed("No version by Adele, so playing Hello instead."))   # worked

    def test_a_failure_always_gets_another_round(self):
        self.assertTrue(brain.needs_another_round("play xyz", ["Couldn't find a song called 'xyz'."], True))
        self.assertTrue(brain.needs_another_round("play xyz", ["Couldn't find a song called 'xyz'."], False))

    def test_joining_word_after_one_tool_on_the_first_round(self):
        self.assertTrue(brain.needs_another_round("play halo then open notes", ["Playing Halo."], True))
        self.assertTrue(brain.needs_another_round("pause and also set volume to 20", ["Paused."], True))

    def test_no_extra_round_when_it_already_did_both_or_already_went_again(self):
        self.assertFalse(brain.needs_another_round("play halo and open notes",
                                                   ["Playing Halo.", "Opened Notes."], True))   # did both at once
        self.assertFalse(brain.needs_another_round("play halo and open notes", ["Opened Notes."], False))
        self.assertFalse(brain.needs_another_round("play halo", ["Playing Halo."], True))
        self.assertFalse(brain.needs_another_round("play brandy", ["Playing Brandy."], True))   # "and" inside a word


class TheModelIsToldToDoItAllAtOnce(unittest.TestCase):
    def test_new_conversation_includes_the_one_go_rule(self):
        with mock.patch("brain.playlist_note", return_value=""):
            system = brain.new_conversation()[0]["content"]
        self.assertIn(brain.ONE_GO_RULE, system)


if __name__ == "__main__":
    unittest.main()
