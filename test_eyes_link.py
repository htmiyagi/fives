"""Tests for the tab requests in eyes_link.py (eyes.py asks hub.py to show a tab).
Run: .venv/bin/python -m unittest test_eyes_link"""

import unittest

import eyes_link


def fresh_head():
    """A blank header, like brand-new shared memory (all zero bytes)."""
    return bytearray(eyes_link.HEAD)


class TabRequests(unittest.TestCase):
    def test_nothing_asked_means_none(self):
        self.assertEqual(eyes_link.read_tab(fresh_head(), 0), (None, 0))

    def test_asked_tab_is_read_once(self):
        buf = fresh_head()
        eyes_link.put_tab(buf, "brain")
        name, last = eyes_link.read_tab(buf, 0)
        self.assertEqual(name, "brain")
        self.assertEqual(eyes_link.read_tab(buf, last), (None, last))   # already answered

    def test_asking_the_same_tab_twice_counts_twice(self):
        buf = fresh_head()
        eyes_link.put_tab(buf, "settings")
        _, last = eyes_link.read_tab(buf, 0)
        eyes_link.put_tab(buf, "settings")
        self.assertEqual(eyes_link.read_tab(buf, last)[0], "settings")

    def test_shorter_name_leaves_no_leftovers(self):
        buf = fresh_head()
        eyes_link.put_tab(buf, "settings")
        eyes_link.put_tab(buf, "eyes")
        self.assertEqual(eyes_link.read_tab(buf, 0)[0], "eyes")

    def test_counter_wraps_around_after_255(self):
        buf = fresh_head()
        buf[eyes_link.TAB_ASKED] = 255
        eyes_link.put_tab(buf, "brain")
        self.assertEqual(buf[eyes_link.TAB_ASKED], 0)
        self.assertEqual(eyes_link.read_tab(buf, 255)[0], "brain")

    def test_tab_request_leaves_the_picture_fields_alone(self):
        buf = fresh_head()
        buf[:13] = bytes(range(1, 14))          # counter, length, "watching": must not change
        eyes_link.put_tab(buf, "brain")
        self.assertEqual(bytes(buf[:13]), bytes(range(1, 14)))

    def test_viewer_reads_a_request_from_real_shared_memory(self):
        viewer = eyes_link.Viewer()
        try:
            self.assertIsNone(viewer.tab_request())
            eyes_link.put_tab(viewer.map, "brain")
            self.assertEqual(viewer.tab_request(), "brain")
            self.assertIsNone(viewer.tab_request())
        finally:
            viewer.close()


if __name__ == "__main__":
    unittest.main()
