"""Tests for the two-finger point and the sticky lock-on in gestures.py.
Run: .venv/bin/python -m unittest test_gestures"""

import unittest

import gestures as g

FINGERS = {"index": (g.INDEX_TIP, g.INDEX_PIP), "middle": (g.MIDDLE_TIP, g.MIDDLE_PIP),
           "ring": (g.RING_TIP, g.RING_PIP), "pinky": (g.PINKY_TIP, g.PINKY_PIP)}


def hand(*out):
    """A fake hand (21 points) with the named fingers sticking out and the rest curled.
    Wrist at the bottom; each middle joint 0.3 away; an out tip 0.6 away, a curled tip 0.15 away."""
    points = [(0.5, 0.5)] * 21
    points[g.WRIST] = (0.5, 1.0)
    for name, (tip, pip) in FINGERS.items():
        points[pip] = (0.5, 0.7)
        points[tip] = (0.5, 0.4) if name in out else (0.5, 0.85)
    return points


class TwoFingerPose(unittest.TestCase):
    def test_index_and_middle_out_is_the_pose(self):
        self.assertTrue(g.two_finger_pose(hand("index", "middle")))

    def test_index_alone_is_not(self):
        self.assertFalse(g.two_finger_pose(hand("index")))

    def test_open_hand_is_not(self):
        self.assertFalse(g.two_finger_pose(hand("index", "middle", "ring", "pinky")))

    def test_fist_is_not(self):
        self.assertFalse(g.two_finger_pose(hand()))


class LockOnStickiness(unittest.TestCase):
    def test_locks_on_right_away(self):
        lock = g.LockOn(hold=0.3)
        self.assertEqual(lock.update(0.0, "music"), "music")

    def test_a_short_drift_off_keeps_the_lock(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        self.assertEqual(lock.update(0.1, None), "music")
        self.assertEqual(lock.update(0.2, "music"), "music")

    def test_staying_off_long_enough_lets_go(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.update(0.1, None)
        self.assertIsNone(lock.update(0.45, None))

    def test_switches_only_after_hold_on_the_new_window(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        self.assertEqual(lock.update(0.1, "sketch"), "music")
        self.assertEqual(lock.update(0.3, "sketch"), "music")
        self.assertEqual(lock.update(0.41, "sketch"), "sketch")

    def test_coming_back_restarts_the_clock(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.update(0.1, None)         # drift off...
        lock.update(0.2, "music")      # ...and back
        lock.update(0.3, None)         # off again: the clock starts over here
        self.assertEqual(lock.update(0.5, None), "music")

    def test_release_lets_go_at_once(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.release()
        self.assertIsNone(lock.target)


if __name__ == "__main__":
    unittest.main()
