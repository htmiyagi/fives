"""Recording air-written letters and words in draw mode (for teaching Crosshair's letter reader your handwriting).

Turn it on in config.py with LETTER_RECORD = True. Then in draw mode (Cmd+Esc) press REC in the sketch window
(tap the pen key on it). The page shows what to write:
    WRITE:  x      (12 / 104)
Write it with the pen key as usual. Botched it? Press UNDO: the ink goes and you write that one again. When you've lifted the pen and paused for LETTER_DONE_SECONDS, it's saved
and the next prompt appears (that pause-to-advance is also how a future "letters mode" will know a letter is done).

Each sample is saved as one file with BOTH:
  - the RAW hand: every frame's 21 points (x, y), MediaPipe's z, and whether the pen key was down
    -> can be replayed through any future version of draw mode, so the data never goes stale
  - the INK: where draw mode actually put the pen, every frame (what you saw on the page)
    -> exactly what a letter reader will be given today
Files go to LETTER_RECORD_DIR (crosshair/data_letters by default), one per sample:  <label>_<time>.npz

No camera or OpenCV here (eyes.py feeds it), so it's testable on its own.
"""

import random
import time
from pathlib import Path

import numpy as np

LETTERS = list("abcdefghijklmnopqrstuvwxyz")
WORDS = ["the", "and", "data", "model", "class", "notes", "learn", "hand", "write", "quick", "zebra", "jump",
         "vector", "matrix", "proof", "limit", "graph", "fox", "brown", "lazy", "dog", "sixty", "keep", "why"]


class LetterRecorder:
    def __init__(self, folder, what="letters", repeats=4, done_seconds=1.2, seed=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        pool = LETTERS if what == "letters" else WORDS if what == "words" else LETTERS + WORDS
        self.prompts = pool * (repeats if what != "words" else 1)
        random.Random(seed if seed is not None else time.time()).shuffle(self.prompts)
        self.done_seconds = done_seconds
        self.index = 0
        self.saved = 0
        self._clear()

    def _clear(self):
        self.t, self.pts, self.z, self.pen, self.ink = [], [], [], [], []
        self.strokes = 0
        self.last_up = None
        self.was_down = False

    def prompt(self):
        if self.index >= len(self.prompts):
            return "ALL DONE - thanks!  (LETTER_RECORD = False to stop)"
        return f"WRITE:  {self.prompts[self.index]}      ({self.index + 1} / {len(self.prompts)})"

    def feed(self, t, raw_points, zs, pen_down, ink):
        """Call every frame in draw mode. raw_points = 21 (x, y); zs = 21 depths; ink = pen position (x, y).
        Returns the text to show, and the label of a sample if one was just saved (else None)."""
        if self.index >= len(self.prompts):
            return self.prompt(), None
        self.t.append(t)
        self.pts.append(raw_points)
        self.z.append(zs)
        self.pen.append(bool(pen_down))
        self.ink.append(ink if ink is not None else (np.nan, np.nan))
        if pen_down and not self.was_down:
            self.strokes += 1
        if not pen_down and self.was_down:
            self.last_up = t
        self.was_down = pen_down
        if self.strokes and not pen_down and self.last_up is not None and t - self.last_up >= self.done_seconds:
            return self.prompt(), self._save()
        if not self.strokes and len(self.t) > 30 * 20:       # nothing written for ~20 s: keep the buffer small
            self.t, self.pts, self.z, self.pen, self.ink = (x[-30 * 2:] for x in (self.t, self.pts, self.z, self.pen, self.ink))
        return self.prompt(), None

    def _save(self):
        label = self.prompts[self.index]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        np.savez(self.folder / f"{label}_{stamp}_{self.saved:03d}.npz", label=label,
                 t=np.array(self.t), pts=np.array(self.pts, np.float32), z=np.array(self.z, np.float32),
                 pen=np.array(self.pen), ink=np.array(self.ink, np.float32))
        self.saved += 1
        self.index += 1
        self._clear()
        return label

    def restart(self):
        """Throw away what's been written for THIS prompt (UNDO, or REC just pressed). Same prompt again."""
        self._clear()

    def skip(self):
        """Throw away what's been written for this prompt and move on (for a botched one)."""
        self.index += 1
        self._clear()


if __name__ == "__main__":                               # quick self-test with a fake hand
    import tempfile
    rec = LetterRecorder(tempfile.mkdtemp(), "letters", repeats=1, done_seconds=0.5, seed=0)
    first = rec.prompts[0]
    pts, zs = [(0.5, 0.5)] * 21, [0.0] * 21
    t = 0.0
    for down in [False] * 5 + [True] * 10 + [False] * 5 + [True] * 10 + [False] * 30:
        t += 1 / 30
        text, saved = rec.feed(t, pts, zs, down, (0.5, 0.5))
        if saved:
            break
    files = list(rec.folder.glob("*.npz"))
    d = np.load(files[0])
    print("saved", saved, "==", first, "| strokes:", int(np.sum(np.diff(d["pen"].astype(int)) == 1)),
          "| frames:", len(d["t"]), "| next:", rec.prompt())
