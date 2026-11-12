"""
eyes_link.py - how eyes.py shows its picture INSIDE the FIVES window (hub.py) instead of in a window of its own.

Two programs can't draw in the same window. So they share a piece of memory instead (RAM only, nothing on disk):

    eyes.py  --- each finished HUD picture --->  [ shared memory ]  --- newest picture --->  hub.py's EYES tab
    eyes.py  <--------------- "key 99" lines on eyes.py's stdin (the keys you press) ------  hub.py
    eyes.py  --- "show the BRAIN tab" (a wheel wedge was clicked) --->  [ shared memory ]  --->  hub.py

The picture is not changed on the way: the exact pixels eyes.py would have put in its own window are copied
across as a .bmp (a picture format with no compression, so nothing is lost).

Two small classes:
    Sender   used by eyes.py:  .show(picture) hands one picture over and returns the key pressed (like cv2.waitKey)
    Viewer   used by hub.py:   .newest() gives the newest picture's bytes, .press("c") sends a key

eyes.py only uses this when hub.py started it (hub.py sets the FIVES_EYES_LINK environment variable).
Run by hand, eyes.py opens its own window exactly as before.

How the sharing stays safe: the first number in the memory is a counter. eyes.py makes it ODD while it is writing
and EVEN when the picture is complete, so hub.py never draws a half-written picture.
"""

import os
import queue
import struct
import sys
import threading
from multiprocessing import shared_memory

ENV = "FIVES_EYES_LINK"          # hub.py puts the shared memory's name here for eyes.py
HEAD = 32                        # bytes at the start: counter (8), picture length (4), "someone is watching" (1),
                                 # tab request counter (1, byte 13), tab name (16, bytes 16-31)
TAB_ASKED = 13                   # goes up by one each time eyes.py asks for a tab
TAB_NAME = slice(16, 32)         # which tab, e.g. b"brain" padded with zero bytes
ROOM = 64 * 1024 * 1024          # the biggest picture that fits (the normal HUD picture is about 11 MB)
NO_KEY = 255                     # what cv2.waitKey(1) & 0xFF gives when no key was pressed


def _attach(name):
    """Open the memory hub.py made. Python has a tidy-up helper that deletes shared memory when the program that
    "owns" it quits; we must tell it this memory is NOT ours, or it would vanish when eyes.py stops
    (and START EYES in the FIVES window couldn't reconnect)."""
    try:
        return shared_memory.SharedMemory(name=name, track=False)        # Python 3.13 and newer
    except TypeError:                                                    # Python 3.12: no such option
        shm = shared_memory.SharedMemory(name=name)
        try:
            from multiprocessing import resource_tracker
            resource_tracker.unregister(shm._name, "shared_memory")
        except Exception:
            pass
        return shm


def put_tab(buf, name: str) -> None:
    """Ask for a tab: write its name first, THEN bump the counter, so hub.py never reads half a name."""
    raw = name.encode()[:16]
    buf[TAB_NAME] = raw + bytes(16 - len(raw))
    buf[TAB_ASKED] = (buf[TAB_ASKED] + 1) % 256


def read_tab(buf, last: int) -> tuple[str | None, int]:
    """(the tab asked for, or None if nothing new since `last`; the counter to pass next time)."""
    asked = buf[TAB_ASKED]
    if asked == last:
        return None, last
    return bytes(buf[TAB_NAME]).rstrip(b"\0").decode(errors="ignore"), asked


class Sender:
    """eyes.py's side: hands each picture to the FIVES window and hears which keys were pressed there."""

    def __init__(self, name):
        import cv2                                   # only eyes.py needs OpenCV here
        self.cv2 = cv2
        self.shm = _attach(name)
        self.map = self.shm.buf
        self.seq = struct.unpack_from("<Q", self.map, 0)[0] | 1      # carry on counting from where it was (kept odd)
        self.keys = queue.Queue()
        self.warned = False
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        """The FIVES window writes one line per key press: "key 99" (99 is the letter c)."""
        try:
            for line in sys.stdin:
                parts = line.split()
                if len(parts) == 2 and parts[0] == "key" and parts[1].isdigit():
                    self.keys.put(int(parts[1]) & 0xFF)
        except Exception:
            pass
        self.keys.put(ord("q"))                      # the FIVES window hung up (closed or crashed): quit too

    def ask_tab(self, name: str) -> None:
        """Ask the FIVES window to show one of its tabs (brain, eyes, settings) and come to the front."""
        put_tab(self.map, name)

    def show(self, picture) -> int:
        """Like cv2.imshow + cv2.waitKey in one: pass the picture on, return the key pressed (NO_KEY = none)."""
        if self.map[12]:                             # skip the copying while nobody is looking at the EYES tab
            ok, bmp = self.cv2.imencode(".bmp", picture)
            n = int(bmp.size) if ok else 0
            if 0 < n <= ROOM:
                self.seq += 2                        # stays odd: "writing"
                struct.pack_into("<Q", self.map, 0, self.seq)
                self.map[HEAD:HEAD + n] = memoryview(bmp.reshape(-1))
                struct.pack_into("<I", self.map, 8, n)
                struct.pack_into("<Q", self.map, 0, self.seq + 1)       # even: "complete"
            elif not self.warned:
                self.warned = True
                print("eyes: the picture is too big to show in the FIVES window (lower HUD_SCALE in config.py)")
        try:
            return self.keys.get_nowait()
        except queue.Empty:
            return NO_KEY


def sender():
    """For eyes.py: a Sender if the FIVES window started us, else None (then eyes.py opens its own window)."""
    name = os.environ.get(ENV)
    if not name:
        return None
    try:
        return Sender(name)
    except Exception as err:
        print(f"eyes: couldn't connect to the FIVES window ({err}); opening my own window instead")
        return None


class Viewer:
    """hub.py's side: makes the shared memory, reads the newest picture from it, sends keys to eyes.py."""

    def __init__(self):
        self.shm = shared_memory.SharedMemory(create=True, size=HEAD + ROOM)   # room for the biggest picture;
        self.name = self.shm.name                                              # the Mac only uses what gets written
        self.map = self.shm.buf
        self.seen = 0                                # the counter of the last picture we handed out
        self.asked = 0                               # the tab-request counter we last answered

    def env(self) -> dict:
        """The environment to start eyes.py with, so it knows where the shared memory is."""
        return {**os.environ, ENV: self.name}

    def watch(self, on: bool) -> None:
        """Tell eyes.py whether anyone is looking (it skips the copying when not, to save battery)."""
        self.map[12] = 1 if on else 0

    def newest(self):
        """The newest complete picture as .bmp bytes, or None if there is nothing new since last time."""
        seq, length = struct.unpack_from("<QI", self.map, 0)
        if seq == self.seen or seq % 2 or not 0 < length <= ROOM:
            return None
        data = bytes(self.map[HEAD:HEAD + length])   # our own copy
        if struct.unpack_from("<Q", self.map, 0)[0] != seq:
            return None                              # eyes.py started the next picture while we copied: next time
        self.seen = seq
        return data

    def tab_request(self) -> str | None:
        """The tab eyes.py asked for since last time (e.g. "brain"), or None."""
        name, self.asked = read_tab(self.map, self.asked)
        return name

    def forget(self) -> None:
        """Ignore whatever is in the memory right now (a leftover picture from an eyes.py that has since stopped)."""
        self.seen = struct.unpack_from("<Q", self.map, 0)[0]

    @staticmethod
    def press(proc, char: str) -> bool:
        """Send one key press to eyes.py (proc = the running eyes.py). False if it is gone."""
        try:
            proc.stdin.write(f"key {ord(char[0])}\n")
            proc.stdin.flush()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Give the memory back (hub.py does this when FIVES closes)."""
        try:
            self.map = None
            self.shm.close()
            self.shm.unlink()
        except Exception:
            pass
