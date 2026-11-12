"""Tests for the pure parts of hotkey.py (no keyboard listener needed).
Run: .venv/bin/python -m unittest test_hotkey"""

import unittest
from types import SimpleNamespace

import hotkey


class KeyNames(unittest.TestCase):
    def test_named_key_keeps_its_name(self):
        self.assertEqual(hotkey.key_name(SimpleNamespace(name="alt_l")), "alt_l")

    def test_number_key_is_found_by_its_key_code(self):
        self.assertEqual(hotkey.key_name(SimpleNamespace(vk=19, char="2")), "2")

    def test_option_number_still_reads_as_the_number(self):
        # with Option held, macOS reports the symbol (™) as the character, but the key code is still 2's
        self.assertEqual(hotkey.key_name(SimpleNamespace(vk=19, char="™")), "2")

    def test_other_letter_keys_mean_nothing(self):
        self.assertEqual(hotkey.key_name(SimpleNamespace(vk=0, char="a")), "")

    def test_option_plus_number_is_a_valid_combo(self):
        watcher = hotkey.HotkeyWatcher(["option", "3"])     # would raise ValueError if "3" were unknown
        self.assertIn("3", watcher.keys)


class Hiding(unittest.TestCase):
    def test_number_hidden_while_option_is_held(self):
        self.assertTrue(hotkey.should_hide("2", frozenset(), frozenset({"2"}), option_down=True))

    def test_plain_number_still_types(self):
        self.assertFalse(hotkey.should_hide("2", frozenset(), frozenset({"2"}), option_down=False))

    def test_number_with_no_wedge_still_types_its_symbol(self):
        self.assertFalse(hotkey.should_hide("9", frozenset(), frozenset({"1", "2"}), option_down=True))

    def test_always_hidden_keys_still_hidden(self):
        self.assertTrue(hotkey.should_hide("alt_l", frozenset({"alt_l"}), frozenset(), option_down=False))


if __name__ == "__main__":
    unittest.main()
