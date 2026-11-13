"""Tests for score_gestures.py and the speed math in gestures.py. Run: .venv/bin/python -m unittest test_scoring"""

import unittest

import gestures as g
import score_gestures as sg


def still_hand(shift_tips=0.0, shift_all=0.0):
    """A fake hand: palm landmarks in one spot, fingertips shifted sideways by shift_tips, everything by shift_all."""
    points = [(0.5 + shift_all, 0.5)] * 21
    points[g.WRIST] = (0.5 + shift_all, 1.0)                 # hand size = wrist to middle knuckle = 0.5
    for i in g.FLICK_TIPS:
        points[i] = (0.5 + shift_all + shift_tips, 0.3)
    return points


def recording(frames, seconds=None):
    """frames: [(t, points or None)] -> the dict shape gesture_recorder saves."""
    as_saved = [{"t": t, "p": [[x, y, 0.0] for x, y in p] if p else None} for t, p in frames]
    return {"label": "x", "seconds": seconds if seconds is not None else frames[-1][0], "fps": 30, "frames": as_saved}


class FakeDetector:
    """Fires "right" at the times it's told to."""
    def __init__(self, fire_at=()):
        self.fire_at = set(fire_at)
        self.missed = []

    def update(self, t, points):
        return "right" if t in self.fire_at else None

    def miss(self, t):
        self.missed.append(t)


class Speeds(unittest.TestCase):
    def test_fingers_moving_on_a_still_palm_is_all_relative(self):
        palm_vx, _, rel_vx, _ = g.hand_speeds(still_hand(), still_hand(shift_tips=0.1), dt=0.1)
        self.assertAlmostEqual(palm_vx, 0.0)
        self.assertAlmostEqual(rel_vx, 2.0)          # 0.1 moved / 0.1 s / 0.5 hand size = 2 hand sizes per second

    def test_whole_hand_moving_has_no_relative_speed(self):
        palm_vx, _, rel_vx, _ = g.hand_speeds(still_hand(), still_hand(shift_all=0.1), dt=0.1)
        self.assertAlmostEqual(palm_vx, 2.0)
        self.assertAlmostEqual(rel_vx, 0.0)

    def test_zero_time_is_zero_speed(self):
        self.assertEqual(g.hand_speeds(still_hand(), still_hand(shift_tips=0.1), dt=0), (0.0, 0.0, 0.0, 0.0))


class Replay(unittest.TestCase):
    def test_lost_frames_are_passed_on_as_misses(self):
        det = FakeDetector()
        sg.replay(det, recording([(0.0, still_hand()), (0.1, None), (0.2, still_hand())]))
        self.assertEqual(det.missed, [0.1])

    def test_motion_end_is_after_the_peak(self):
        tips = [0.0, 0.0, 0.05, 0.2, 0.3, 0.31, 0.31]         # a fast move between 0.1 and 0.3 s, then still
        rec = recording([(i * 0.05 + 0.0, still_hand(shift_tips=s)) for i, s in enumerate(tips)])
        end = sg.motion_end(rec)
        self.assertGreater(end, 0.15)
        self.assertLessEqual(end, 0.3)


class Scoring(unittest.TestCase):
    def test_hits_misses_and_false_alarms_are_counted(self):
        hit = recording([(0.0, still_hand()), (0.1, still_hand())])
        miss = recording([(0.0, still_hand()), (0.2, still_hand())])
        normal = recording([(0.0, still_hand()), (0.1, still_hand())], seconds=60)
        result = sg.score(lambda: FakeDetector(fire_at=[0.1]),
                          [("flick/a.json", hit), ("flick/b.json", miss)], [("not/c.json", normal)])
        self.assertEqual(result["hits"], 1)
        self.assertEqual(result["missed"], ["flick/b.json"])
        self.assertEqual(result["false"], [("not/c.json", 0.1)])
        self.assertAlmostEqual(result["not_minutes"], 1.0)

    def test_report_mentions_the_numbers(self):
        result = {"attempts": 10, "hits": 9, "missed": ["flick/x.json"], "doubles": [], "lags": [0.05],
                  "not_minutes": 10.0, "false": [("not/y.json", 3.2)]}
        text = sg.report("test", "a test", result)
        self.assertIn("9/10 = 90%", text)
        self.assertIn("1 in 10.0 min = 0.10/min", text)
        self.assertIn("+50 ms", text)
        self.assertIn("flick/x.json", text)

    def test_collision_check_reads_zero_as_ok(self):
        result = {"attempts": 5, "hits": 0, "missed": [], "doubles": [], "lags": [], "not_minutes": 0, "false": []}
        self.assertIn("0/5   (ok)", sg.report("palm", "check", result, should_fire=False))

    def test_known_detectors_can_be_made(self):
        for name, (_, make, _) in sg.detectors().items():
            self.assertTrue(hasattr(make(), "update"), name)


if __name__ == "__main__":
    unittest.main()
