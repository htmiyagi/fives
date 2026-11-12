"""
Tests for the wheel: the order rules and math (wheel_logic.py) and the wheel's actions (actions.py).
No window opens: the actions are tested with a FakeWindow that just writes down what it was told.

Run them:   .venv/bin/python -m unittest test_wheel -v
"""

import unittest

import actions
import settings
import wheel_logic as wl

CX, CY, INNER, OUTER = 200, 200, 60, 190      # a wheel centred at (200, 200)


class FakeWindow:
    """Pretends to be a FIVES window. send() writes the word down instead of moving anything."""
    def __init__(self):
        self.sent = []
        self.frame = (0, 0, 100, 100)

    def send(self, word):
        self.sent.append(word)


class Order(unittest.TestCase):
    def test_default_order_passes_unchanged(self):
        self.assertEqual(wl.clean_order(wl.DEFAULT_ORDER), wl.DEFAULT_ORDER)

    def test_settings_default_matches_the_wheel_default(self):
        self.assertEqual(settings.DEFAULTS["wheel_order"], wl.DEFAULT_ORDER)

    def test_unknown_windows_and_repeats_are_dropped(self):
        self.assertEqual(wl.clean_order(["music", "fridge", "music", "settings"]), ["music", "settings"])

    def test_settings_is_put_back_if_missing(self):
        self.assertEqual(wl.clean_order(["music", "brain"]), ["music", "brain", "settings"])

    def test_settings_can_be_moved(self):
        self.assertEqual(wl.clean_order(["settings", "music"]), ["settings", "music"])

    def test_only_settings_falls_back_to_default(self):
        self.assertEqual(wl.clean_order(["settings"]), wl.DEFAULT_ORDER)

    def test_garbage_falls_back_to_default(self):
        for junk in (None, "music", 42, {}):
            self.assertEqual(wl.clean_order(junk), wl.DEFAULT_ORDER)

    def test_never_more_than_max_and_settings_survives(self):
        many = {f"w{i}": f"W{i}" for i in range(10)}
        original = dict(wl.WINDOWS)
        try:
            wl.WINDOWS.update(many)                              # pretend FIVES has lots of windows
            order = wl.clean_order(list(many) + ["settings"])    # 11 asked for, Settings last
            self.assertEqual(len(order), wl.MAX_WEDGES)
            self.assertIn("settings", order)
        finally:
            wl.WINDOWS.clear()
            wl.WINDOWS.update(original)

    def test_the_saved_list_is_not_changed(self):
        saved = ["music", "music"]
        wl.clean_order(saved)
        self.assertEqual(saved, ["music", "music"])


class Geometry(unittest.TestCase):
    def test_straight_up_is_wedge_zero(self):
        self.assertEqual(wl.wedge_at(CX, CY - 120, CX, CY, INNER, OUTER, 5), 0)

    def test_clockwise_order(self):
        # 4 wedges: up = 0, right = 1, down = 2, left = 3 (y grows downward)
        self.assertEqual(wl.wedge_at(CX + 120, CY, CX, CY, INNER, OUTER, 4), 1)
        self.assertEqual(wl.wedge_at(CX, CY + 120, CX, CY, INNER, OUTER, 4), 2)
        self.assertEqual(wl.wedge_at(CX - 120, CY, CX, CY, INNER, OUTER, 4), 3)

    def test_wedge_zero_is_centred_on_up(self):
        # just left of straight up is still wedge 0, not the last wedge
        self.assertEqual(wl.wedge_at(CX - 20, CY - 150, CX, CY, INNER, OUTER, 4), 0)

    def test_hole_and_outside_are_no_wedge(self):
        self.assertIsNone(wl.wedge_at(CX, CY, CX, CY, INNER, OUTER, 5))
        self.assertIsNone(wl.wedge_at(CX, CY - 300, CX, CY, INNER, OUTER, 5))
        self.assertIsNone(wl.wedge_at(CX, CY - 120, CX, CY, INNER, OUTER, 0))

    def test_every_wedge_middle_maps_back_to_itself(self):
        for count in range(2, wl.MAX_WEDGES + 1):
            for i in range(count):
                x, y = wl.point_at(wl.wedge_middle(i, count), 120, CX, CY)
                self.assertEqual(wl.wedge_at(x, y, CX, CY, INNER, OUTER, count), i)


class Growth(unittest.TestCase):
    def test_nothing_hovered_means_normal_size(self):
        self.assertEqual([wl.growth(i, None, 5) for i in range(5)], [1.0] * 5)

    def test_hovered_grows_most_and_neighbours_a_little_wrapping_around(self):
        sizes = [wl.growth(i, 0, 5) for i in range(5)]
        self.assertEqual(sizes[0], 1 + wl.HOVER_GROW)
        self.assertEqual(sizes[1], 1 + wl.NEIGHBOR_GROW)
        self.assertEqual(sizes[4], 1 + wl.NEIGHBOR_GROW)      # the last wedge sits next to the first
        self.assertEqual(sizes[2], 1.0)


class WheelActions(unittest.TestCase):
    def setUp(self):
        self.saved = dict(actions._windows)
        actions._windows.clear()

    def tearDown(self):
        actions._windows.clear()
        actions._windows.update(self.saved)

    def test_the_wheel_actions_are_registered(self):
        self.assertTrue({"open_wheel", "close_wheel", "open_window", "hide_window"} <= set(actions.ACTIONS))

    def test_open_and_close_the_wheel(self):
        wheel = FakeWindow()
        actions.connect_window("wheel", wheel)
        self.assertEqual(actions.run("open_wheel"), "Wheel opened.")
        self.assertEqual(actions.run("close_wheel"), "Wheel closed.")
        self.assertEqual(wheel.sent, ["show", "hide"])

    def test_open_and_hide_a_window_by_name(self):
        music = FakeWindow()
        actions.connect_window("music", music)
        self.assertEqual(actions.run("open_window", window=" Music "), "Music window opened.")
        self.assertEqual(actions.run("hide_window", window="music"), "Music window put away.")
        self.assertEqual(music.sent, ["show", "hide"])

    def test_hiding_sketch_forgets_where_it_was(self):
        sketch = FakeWindow()
        actions.connect_window("sketch", sketch)
        actions.run("hide_window", window="sketch")
        self.assertEqual(sketch.sent, ["hide"])
        self.assertIsNone(sketch.frame)

    def test_unknown_or_missing_windows_return_a_sentence(self):
        self.assertEqual(actions.run("open_window", window="fridge"), "FIVES has no window called 'fridge'.")
        self.assertEqual(actions.run("open_window", window="brain"), "The brain window isn't running.")
        self.assertEqual(actions.run("open_wheel"), "The wheel window isn't running.")

    def test_every_wheel_window_can_be_asked_for(self):
        for name in wl.WINDOWS:
            said = actions.run("open_window", window=name)
            self.assertFalse(said.startswith("FIVES has no window"), name)


if __name__ == "__main__":
    unittest.main()
