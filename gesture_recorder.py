"""
gesture_recorder.py - records hand points (never pictures) so a gesture detector can be replayed and scored.

    tap a record key ──▶ ● REC flick ──▶ every camera frame: add(t, points, zs) ──▶ tap again ──▶ saved

Saved as  recordings/<label>/<date>_<time>.json  (the recordings/ folder is gitignored):
    {"label": "flick", "seconds": 1.3, "fps": 29.6, "frames": [{"t": 0.0, "p": [[x, y, z], ...21]}, {"t": 0.034, "p": null}]}
"t" counts from the start of the recording. "p": null means no hand was found in that frame.

No camera or OpenCV here, so it can be tested on its own. eyes.py feeds it frames.
See GESTURES.md ("Tools to build first") for how the recordings get used.
"""

import json
import time
from pathlib import Path

MIN_FRAMES = 3              # shorter than this = a mis-tap, not a recording: thrown away
DIGITS = 5                  # decimals kept for each number (plenty for 0..1 camera points)


class GestureRecorder:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.label = None       # what we're recording right now ("flick", "not"), or None
        self.frames = []
        self.t0 = None          # the time of the first frame
        self.started = ""       # wall-clock time, for the file name

    def toggle(self, label: str) -> str:
        """Tap a record key: start recording `label`, or stop if that label is already recording.
        (Tapping a different label's key stops the current one and starts the new one.)"""
        if self.label == label:
            return self.stop()
        said = self.stop() + "\n" if self.label else ""
        self.label, self.frames, self.t0 = label, [], None
        self.started = time.strftime("%Y-%m-%d_%H-%M-%S")
        return said + f"● recording '{label}'... tap the same key again to stop"

    def add(self, t: float, points=None, zs=None) -> None:
        """One camera frame. points = 21 (x, y) pairs, or None if no hand was found."""
        if self.label is None:
            return
        if self.t0 is None:
            self.t0 = t
        if points is None:
            pts = None
        else:
            depth = zs if zs is not None else [0.0] * len(points)
            pts = [[round(x, DIGITS), round(y, DIGITS), round(z, DIGITS)] for (x, y), z in zip(points, depth)]
        self.frames.append({"t": round(t - self.t0, DIGITS), "p": pts})

    def stop(self) -> str:
        """Stop and save. Returns what happened, in one line."""
        if self.label is None:
            return "not recording"
        label, frames = self.label, self.frames
        self.label, self.frames = None, []
        if len(frames) < MIN_FRAMES:
            return f"'{label}' recording too short ({len(frames)} frames): not saved"
        seconds = frames[-1]["t"]
        fps = (len(frames) - 1) / seconds if seconds > 0 else 0.0
        path = unique_path(self.folder / label, self.started)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"label": label, "seconds": seconds, "fps": round(fps, 1),
                                        "frames": frames}))
        except OSError as err:
            return f"couldn't save the '{label}' recording: {err}"
        count = len(list(path.parent.glob("*.json")))
        return f"saved '{label}' #{count}: {len(frames)} frames, {seconds:.1f} s, {fps:.0f} fps -> {path.name}"


def unique_path(folder, name: str) -> Path:
    """folder/name.json, or name_2.json, name_3.json... if that's taken (two recordings in the same second)."""
    path, n = Path(folder) / f"{name}.json", 1
    while path.exists():
        n += 1
        path = Path(folder) / f"{name}_{n}.json"
    return path


def load(path) -> dict:
    """Read one recording back (the replay scorer uses this)."""
    return json.loads(Path(path).read_text())
