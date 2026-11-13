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

    def test_recent_remembers_a_window_just_left(self):
        # a fast swipe: the cursor leaves the window and the lock lets go before the swipe is finished
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.update(0.1, None)
        lock.update(0.45, None)                        # let go at 0.45
        self.assertEqual(lock.recent(0.7, within=0.5), "music")

    def test_recent_forgets_after_the_grace(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.update(0.1, None)
        lock.update(0.45, None)
        self.assertIsNone(lock.recent(1.0, within=0.5))

    def test_recent_forgets_a_window_that_was_put_away(self):
        lock = g.LockOn(hold=0.3)
        lock.update(0.0, "music")
        lock.release()                                 # swiped away: don't swipe it again
        self.assertIsNone(lock.recent(0.1, within=0.5))


def slide(detector, points, start_t, dx_total, frames=7, step=0.05):
    """Move a fake hand sideways by dx_total over a few frames. Returns the first swipe seen (or None)."""
    seen = None
    for i in range(frames):
        shift = dx_total * i / (frames - 1)
        moved = [(x + shift, y) for x, y in points]
        seen = seen or detector.update(start_t + i * step, moved)
    return seen


def two_finger_flick():
    return g.FlickDetector(distance=1.0, seconds=0.5, cooldown=0.3, pose=g.two_finger_pose)


class TwoFingerSwipe(unittest.TestCase):
    def test_two_finger_slide_is_a_swipe(self):
        self.assertEqual(slide(two_finger_flick(), hand("index", "middle"), 0.0, 0.6), "right")

    def test_open_palm_slide_is_not_a_two_finger_swipe(self):
        self.assertIsNone(slide(two_finger_flick(), hand("index", "middle", "ring", "pinky"), 0.0, 0.6))

    def test_swipe_back_soon_after_still_counts(self):
        # the undo: right, then left half a second later (a 1 s cooldown would have blocked this)
        detector = two_finger_flick()
        self.assertEqual(slide(detector, hand("index", "middle"), 0.0, 0.6), "right")
        moved_right = [(x + 0.6, y) for x, y in hand("index", "middle")]
        self.assertEqual(slide(detector, moved_right, 0.8, -0.6), "left")



FRAME = 1 / 30                      # 30 fps


def moved(points, tips=0.0, everything=0.0):
    """Shift the index + middle fingertips sideways by `tips`, and the whole hand by `everything`."""
    out = [(x + everything, y) for x, y in points]
    for i in (g.INDEX_TIP, g.MIDDLE_TIP):
        out[i] = (out[i][0] + tips, out[i][1])
    return out


def play(detector, frames, start=0.0):
    """frames: hands (or None = lost frame), one per 1/30 s. Returns every direction the detector fired."""
    fired = []
    for i, points in enumerate(frames):
        t = start + i * FRAME
        if points is None:
            detector.miss(t)
        else:
            fired += [d for d in [detector.update(t, points)] if d]
    return fired


V = hand("index", "middle")         # ✌️ (hand size 0.5)
HOLD = [V] * 4                      # holding the ✌️ still: arms the detector


def finger_flick(step=0.15, everything=0.0):
    """The fingertips snap sideways by `step` per frame (relative to the palm) for 3 frames."""
    return [moved(V, tips=step * k, everything=everything * k) for k in range(1, 4)]


def detector():
    return g.FingerFlickDetector(speed=6.0, palm_max=2.0, seconds=0.15, arm_frames=3, sideways=1.0,
                                 grace=0.08, cooldown=0.4)


class FingerFlick(unittest.TestCase):
    def test_flick_from_a_held_point_fires_once(self):
        self.assertEqual(play(detector(), HOLD + finger_flick()), ["right"])

    def test_direction_follows_the_fingers(self):
        self.assertEqual(play(detector(), HOLD + finger_flick(step=-0.15)), ["left"])

    def test_too_slow_does_not_fire(self):
        self.assertEqual(play(detector(), HOLD + finger_flick(step=0.03)), [])

    def test_returning_to_the_center_after_a_flick_does_not_undo(self):
        # flick right, then the whole hand drifts back left toward the screen's center (still in ✌️)
        det = detector()
        play(det, HOLD + finger_flick())
        flicked = moved(V, tips=0.45)
        drift_back = [moved(flicked, everything=-0.15 * k) for k in range(1, 8)]
        self.assertEqual(play(det, drift_back, start=7 * FRAME), [])

    def test_stop_then_flick_back_does_undo(self):
        # flick right, STOP in ✌️ for a moment (re-arms), then flick the fingers back left
        det = detector()
        play(det, HOLD + finger_flick())
        stop_and_flick_back = HOLD * 4 + finger_flick(step=-0.15)          # 16 still frames = past the cooldown
        self.assertEqual(play(det, stop_and_flick_back, start=7 * FRAME), ["left"])

    def test_no_point_first_does_not_fire(self):
        index_only = hand("index")
        frames = [index_only] * 4 + [moved(index_only, tips=0.15 * k) for k in range(1, 4)]
        self.assertEqual(play(detector(), frames), [])

    def test_whole_hand_swipe_is_not_a_finger_flick(self):
        swipe = [moved(V, everything=0.15 * k) for k in range(1, 4)]       # fingers and palm move together
        self.assertEqual(play(detector(), HOLD + swipe), [])

    def test_fast_fingers_on_a_moving_palm_do_not_fire(self):
        self.assertEqual(play(detector(), HOLD + finger_flick(step=0.15, everything=0.1)), [])

    def test_one_lost_frame_mid_flick_is_forgiven(self):
        flick = finger_flick()
        self.assertEqual(play(detector(), HOLD + [flick[0], None, flick[2]]), ["right"])

    def test_must_point_again_before_the_next_flick(self):
        det = detector()
        play(det, HOLD + finger_flick())
        back = [moved(V, tips=0.45 - 0.15 * k) for k in range(1, 4)]       # fingers swing straight back
        self.assertEqual(play(det, back, start=7 * FRAME), [])

    def test_debug_line_says_why_it_did_not_fire(self):
        self.assertIn("lower FINGER_FLICK_SPEED", g.finger_flick_report((4.2, 0.5), 6.0, 2.0))
        self.assertIn("palm moved too much", g.finger_flick_report((7.0, 3.0), 6.0, 2.0))


class OldGesturesIgnoreTheFingerFlick(unittest.TestCase):
    """GESTURES.md: each new gesture ships with a test that the old ones don't fire on it."""

    def test_palm_swipe_for_the_wheel_ignores_it(self):
        palm = g.FlickDetector(distance=0.7, seconds=0.45, cooldown=1.0, palm_factor=1.15)
        self.assertEqual(play(palm, HOLD + finger_flick()), [])

    def test_finger_flick_ignores_an_open_palm_swipe(self):
        open_hand = hand("index", "middle", "ring", "pinky")
        swipe = [moved(open_hand, everything=0.15 * k) for k in range(1, 6)]
        self.assertEqual(play(detector(), [open_hand] * 4 + swipe), [])


if __name__ == "__main__":
    unittest.main()
