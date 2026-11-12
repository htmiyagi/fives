"""
Tests for settings.py.   Run them:   .venv/bin/python -m unittest test_settings -v

Uses a throwaway settings file, so your real settings.json is never touched.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "settings.json"
        for name, value in (("FILE", self.file), ("_cache", None), ("_cache_time", None)):
            patcher = mock.patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def save_from_another_program(self, saved: dict, stamp: float):
        """Pretend the FIVES window saved the file (stamp = when, so the change is clearly newer)."""
        self.file.write_text(json.dumps(saved))
        os.utime(self.file, (stamp, stamp))

    def test_defaults_when_there_is_no_file(self):
        self.assertEqual(settings.get("play_order"), "Shuffle")

    def test_a_change_saved_by_another_program_is_seen(self):      # the window and the chat are separate
        self.save_from_another_program({"play_order": "Shuffle"}, 1_000)
        self.assertEqual(settings.get("play_order"), "Shuffle")
        self.save_from_another_program({"play_order": "In order"}, 2_000)
        self.assertEqual(settings.get("play_order"), "In order")

    def test_a_choice_that_no_longer_exists_falls_back(self):
        self.save_from_another_program({"play_order": "Backwards"}, 1_000)
        self.assertEqual(settings.get("play_order"), "Shuffle")

    def test_put_saves_and_reads_back(self):
        settings.put("play_order", "As is")
        self.assertEqual(json.loads(self.file.read_text())["play_order"], "As is")
        self.assertEqual(settings.get("play_order"), "As is")


if __name__ == "__main__":
    unittest.main()
