"""GRIP PEN: write by holding an invisible pen and pushing it to an invisible sheet of paper. No key.

Trained in Crosshair (lessons 33-34) on your own recordings:
  - PEN GRIP? a small model reads the hand's shape (finger curls, thumb/index/middle tips: the "tripod").
    96% right; mistakes your pointing hand for a pen 1-2% of the time.
  - ON THE PAPER? hand size ("whole palm": the palm bones averaged). Closer to the camera = bigger.
    Pushed forward = ink on, pulled back a little = ink off (like lifting a real pen). 96-98% right.
Ink goes down only when BOTH say yes, for CONFIRM frames in a row (a one-frame wobble can't draw a dot),
and lifts after RELEASE frames of either saying no. Two depth lines (on / off) with a gap, so it doesn't flicker.

Where the pen is: the "nib", halfway between your thumb tip and index tip (where a real pen's tip would be),
or "knuckle" (your index knuckle: steadier, since it doesn't move when your fingers flex). config.DRAW_GRIP_POINT.

SET THE PAPER (tap the pen key, Option): hold the pen grip where you want to write and tap it. That hand size
becomes "the paper", and the lines get much tighter and follow YOU instead of the trained average:
    ink ON   when you're within TOUCH (3%) of the paper, with the pen grip
    ink OFF  when you pull back LIFT (6%) from where you were during this stroke
             (so a small pull-back always lifts, whether you were pushing hard or soft)
    while you write, the paper slowly follows where your hand actually is (it drifts as you write).
Before you set it, the trained lines from lesson 34 are used.

No camera or OpenCV here (eyes.py feeds it), numpy only.
"""

import numpy as np

FINGERS = [(5, 8), (9, 12), (13, 16), (17, 20)]       # (knuckle, tip): index, middle, ring, pinky


def palm_size(points):
    p = np.asarray(points, float)
    d = lambda a, b: float(np.hypot(*(p[a] - p[b])))
    return (d(0, 5) + d(0, 9) + d(0, 13) + d(0, 17) + d(5, 17)) / 5


def handmade(points, zs):
    """The same 9 numbers as Crosshair's lesson 34 (finger curls, tripod, thumb near the index base)."""
    p = np.concatenate([np.asarray(points, float), np.asarray(zs, float)[:, None]], 1)
    size = palm_size(points)
    d = lambda a, b: float(np.linalg.norm(p[a] - p[b]))
    out = [d(0, tip) / max(d(0, k), 1e-6) for k, tip in FINGERS]
    out += [d(4, 8) / size, d(4, 12) / size, d(8, 12) / size, d(4, 5) / size, d(4, 6) / size]
    return np.array(out)


class GripPen:
    def __init__(self, path, confirm=2, release=3, point="nib", vote=5, touch=0.03, lift=0.06):
        m = np.load(path)
        self.W1, self.b1, self.W2, self.b2 = m["W1"], m["b1"], m["W2"], m["b2"]
        self.mu, self.sd = m["mu"], m["sd"]
        self.on_line, self.off_line = float(m["on_line"]), float(m["off_line"])
        self.confirm, self.release, self.point, self.vote = confirm, release, point, vote
        self.touch, self.lift = touch, lift
        self.paper = None                                # set by set_paper(): your own paper (hand size)
        self.reset()

    def set_paper(self, points):
        """'This is where I write': the current hand size becomes the paper."""
        self.paper = palm_size(points)
        self.peak = self.paper
        return self.paper

    def reset(self):
        self.down = False
        self.yes = self.no = 0
        self.recent = []
        self.grip = False
        self.size = 0.0
        self.peak = 0.0                                  # biggest hand size during the current stroke

    def grip_chance(self, points, zs):
        x = (handmade(points, zs) - self.mu) / self.sd
        h = np.maximum(0, self.W1 @ x + self.b1)
        s = self.W2 @ h + self.b2
        e = np.exp(s - s.max())
        return float(e[1] / e.sum())                     # chance it's a pen grip

    def nib(self, points):
        if self.point == "knuckle":
            return points[5]
        (ax, ay), (bx, by) = points[4], points[8]
        return ((ax + bx) / 2, (ay + by) / 2)

    def update(self, points, zs):
        """Call every frame the hand is seen. Returns True while the ink should be down."""
        self.recent = (self.recent + [self.grip_chance(points, zs) > 0.5])[-self.vote:]
        self.grip = sum(self.recent) * 2 > len(self.recent)          # majority of the last few frames
        self.size = palm_size(points)
        if self.paper is None:                           # not set yet: the trained lines
            on_paper = self.size >= (self.off_line if self.down else self.on_line)
        elif not self.down:                              # pen up: touch when you're back near the paper
            on_paper = self.size >= self.paper * (1 - self.touch)
        else:                                            # pen down: lift when you pull back from this stroke's peak
            self.peak = max(self.peak, self.size)
            on_paper = self.size >= self.peak * (1 - self.lift)
            self.paper += 0.02 * (self.size - self.paper)    # the paper slowly follows your writing hand
        want = self.grip and on_paper
        if want:
            self.yes, self.no = self.yes + 1, 0
        else:
            self.yes, self.no = 0, self.no + 1
        if not self.down and self.yes >= self.confirm:
            self.down = True
            self.peak = self.size
        elif self.down and self.no >= self.release:
            self.down = False
        return self.down

    def status(self):
        """For the HUD: what the pen thinks right now."""
        grip = "GRIP" if self.grip else "no grip"
        if self.paper is None:
            where = "ON PAPER" if self.size >= self.on_line else "lifted" if self.size < self.off_line else "edge"
            return f"{grip} · {where} {self.size:.3f} (line {self.on_line:.3f}) · tap Option to set your paper"
        away = (self.size / self.paper - 1) * 100
        return f"{grip} · {'INK' if self.down else 'lifted'} · {away:+.0f}% from your paper"
