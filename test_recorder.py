"""Tests for gesture_recorder.py. Run: .venv/bin/python -m unittest test_recorder"""

import tempfile
import unittest
from pathlib import Path

import gesture_recorder as gr

HAND = [(0.5, 0.5)] * 21
DEPTH = [0.01] * 21


class Recording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = gr.GestureRecorder(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self, label):
        return sorted(Path(self.tmp.name, label).glob("*.json"))

    def test_frames_are_ignored_when_not_recording(self):
        self.rec.add(0.0, HAND, DEPTH)
        self.assertEqual(self.rec.frames, [])

    def test_tap_twice_saves_points_and_times(self):
        self.rec.toggle("flick")
        for i in range(5):
            self.rec.add(10.0 + i * 0.05, HAND, DEPTH)
        said = self.rec.toggle("flick")
        self.assertIn("saved 'flick' #1", said)
        data = gr.load(self.saved("flick")[0])
        self.assertEqual(data["label"], "flick")
        self.assertEqual(data["frames"][0]["t"], 0.0)              # times count from the start
        self.assertAlmostEqual(data["frames"][-1]["t"], 0.2)
        self.assertEqual(data["frames"][0]["p"][0], [0.5, 0.5, 0.01])
        self.assertAlmostEqual(data["fps"], 20.0)

    def test_lost_hand_is_saved_as_null(self):
        self.rec.toggle("not")
        self.rec.add(0.0, HAND, DEPTH)
        self.rec.add(0.1)                                          # no hand this frame
        self.rec.add(0.2, HAND, DEPTH)
        self.rec.stop()
        self.assertIsNone(gr.load(self.saved("not")[0])["frames"][1]["p"])

    def test_a_mis_tap_is_not_saved(self):
        self.rec.toggle("flick")
        self.rec.add(0.0, HAND, DEPTH)
        self.assertIn("too short", self.rec.toggle("flick"))
        self.assertEqual(self.saved("flick"), [])

    def test_other_label_key_switches_recording(self):
        self.rec.toggle("flick")
        for i in range(4):
            self.rec.add(i * 0.05, HAND, DEPTH)
        said = self.rec.toggle("not")
        self.assertIn("saved 'flick'", said)
        self.assertEqual(self.rec.label, "not")

    def test_stop_when_idle_says_so(self):
        self.assertEqual(self.rec.stop(), "not recording")


if __name__ == "__main__":
    unittest.main()
