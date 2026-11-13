"""
score_gestures.py - replay every recording through a gesture detector and score it (GESTURES.md "Measuring").

    recordings/flick/*.json  (one real attempt each)  ──▶ hit rate, lag, which ones were missed
    recordings/not/*.json    (normal hand use)        ──▶ false triggers per minute, and when

Run:   .venv/bin/python score_gestures.py                    (every detector)
       .venv/bin/python score_gestures.py point-swipe        (just one)
It uses your current config.py numbers, so: change a number, run again, compare. No camera needed.

Record with Ctrl+Option+F / Ctrl+Option+N while FIVES runs (RECORD_KEYS in config.py).
"""

import statistics
import sys
from pathlib import Path

import config
import gesture_recorder
import gestures as g

FOLDER = Path(__file__).with_name("recordings")
GESTURE = "flick"            # the label of the "done right" recordings
NOT = "not"                  # the label of the "must NOT trigger" recordings
MOTION_END_DROP = 0.5        # the flick "ends" when the fingers' relative speed drops below half its peak
TARGET_HIT_RATE = 0.9        # GESTURES.md starting targets
TARGET_FALSE_PER_MIN = 0.1   # (under 1 per 10 minutes)


def detectors() -> dict:
    """Every detector the scorer knows: name -> (what it is, how to make a fresh one, should it fire on flicks?).
    The palm swipe is here as a collision check: it must NOT fire on flicks (GESTURES.md "No collisions")."""
    return {
        "palm": ("open-palm swipe (the wheel): a collision check",
                 lambda: g.FlickDetector(config.FLICK_DISTANCE, config.FLICK_SECONDS, config.FLICK_COOLDOWN,
                                         palm_factor=config.FLICK_PALM_FACTOR),
                 False),
        "point-swipe": ("✌️ whole-hand swipe from PR #33 (the baseline to beat)",
                        lambda: g.FlickDetector(config.POINT_FLICK_DISTANCE, config.FLICK_SECONDS,
                                                config.POINT_FLICK_COOLDOWN,
                                                pose=lambda pts: g.two_finger_pose(pts, config.POINT_FACTOR)),
                        True),
        "finger-flick": ("✌️ finger flick: fingertips fast relative to a still palm (the new one)",
                         make_finger_flick, True),
        "spin": ("✌️ ↺ spin: a collision check (it must NOT fire on flicks or normal use)", make_spin, False),
    }


def make_finger_flick() -> g.FingerFlickDetector:
    """A finger-flick detector with the current config.py numbers (eyes.py uses this too)."""
    return g.FingerFlickDetector(config.FINGER_FLICK_SPEED, config.FINGER_FLICK_PALM_MAX, config.FINGER_FLICK_SECONDS,
                                 config.FINGER_FLICK_ARM_FRAMES, config.FINGER_FLICK_SIDEWAYS,
                                 config.FINGER_FLICK_GRACE, config.FINGER_FLICK_COOLDOWN, config.POINT_FACTOR)


def make_spin() -> g.SpinDetector:
    """A ✌️ spin detector with the current config.py numbers (eyes.py uses this too)."""
    return g.SpinDetector(config.SPIN_TURN, config.SPIN_SECONDS, config.SPIN_MIN_RADIUS, config.SPIN_COOLDOWN,
                          config.SPIN_GRACE, config.POINT_FACTOR, config.SPIN_ROUNDNESS)


# ---- replaying -------------------------------------------------------------------------------------
def frames_of(recording):
    """(t, points) for each frame. points = 21 (x, y) pairs, or None when no hand was found."""
    for frame in recording["frames"]:
        pts = frame["p"]
        yield frame["t"], ([(x, y) for x, y, _ in pts] if pts else None)


def replay(detector, recording) -> list:
    """Feed a recording to a detector, frame by frame, exactly like eyes.py does. Returns [(t, direction)]."""
    fired = []
    for t, points in frames_of(recording):
        if points is None:
            detector.miss(t)
            continue
        direction = detector.update(t, points)
        if direction:
            fired.append((t, direction))
    return fired


def motion_end(recording):
    """When the flick's motion finished: the first frame after the peak relative fingertip speed where
    it has dropped below MOTION_END_DROP of that peak. None if the recording has too little hand in it."""
    speeds, before = [], None
    for t, points in frames_of(recording):
        if points is None:
            before = None
            continue
        if before is not None:
            _, _, rvx, rvy = g.hand_speeds(before[1], points, t - before[0])
            speeds.append((t, (rvx ** 2 + rvy ** 2) ** 0.5))
        before = (t, points)
    if not speeds:
        return None
    peak_i = max(range(len(speeds)), key=lambda i: speeds[i][1])
    peak = speeds[peak_i][1]
    for t, speed in speeds[peak_i:]:
        if speed < peak * MOTION_END_DROP:
            return t
    return speeds[-1][0]


# ---- scoring ---------------------------------------------------------------------------------------
def score(make_detector, gesture_recs, not_recs) -> dict:
    """gesture_recs / not_recs: [(name, recording)]. A fresh detector for each recording, so they can't leak."""
    result = {"attempts": len(gesture_recs), "hits": 0, "missed": [], "doubles": [], "lags": [],
              "not_minutes": 0.0, "false": []}
    for name, rec in gesture_recs:
        fired = replay(make_detector(), rec)
        if not fired:
            result["missed"].append(name)
            continue
        result["hits"] += 1
        if len(fired) > 1:
            result["doubles"].append(name)
        end = motion_end(rec)
        if end is not None:
            result["lags"].append(fired[0][0] - end)
    for name, rec in not_recs:
        result["not_minutes"] += rec["seconds"] / 60
        result["false"] += [(name, t) for t, _ in replay(make_detector(), rec)]
    return result


def report(name: str, about: str, r: dict, should_fire: bool = True) -> str:
    """The scores as a few readable lines. should_fire=False: a collision check (firing on a flick is bad)."""
    lines = [f"\n== {name}: {about}"]
    if r["attempts"] and not should_fire:
        mark = "ok" if r["hits"] == 0 else "COLLISION: it mistakes flicks for its own gesture"
        lines.append(f"   fired on flicks  {r['hits']}/{r['attempts']}   ({mark})")
        lines += [f"   false alarm   {n} at {t:.1f} s" for n, t in r["false"]]
        return "\n".join(lines)
    if r["attempts"]:
        rate = r["hits"] / r["attempts"]
        mark = "ok" if rate >= TARGET_HIT_RATE else f"target {TARGET_HIT_RATE:.0%}"
        lines.append(f"   hit rate      {r['hits']}/{r['attempts']} = {rate:.0%}   ({mark})")
    if r["lags"]:
        lag = statistics.median(r["lags"]) * 1000
        lines.append(f"   lag           {lag:+.0f} ms median (+ = after the flick ended, - = before)")
    if r["not_minutes"]:
        per_min = len(r["false"]) / r["not_minutes"]
        mark = "ok" if per_min < TARGET_FALSE_PER_MIN else f"target under {TARGET_FALSE_PER_MIN}"
        lines.append(f"   false alarms  {len(r['false'])} in {r['not_minutes']:.1f} min = {per_min:.2f}/min   ({mark})")
    lines += [f"   missed        {n}" for n in r["missed"]]
    lines += [f"   fired twice   {n}" for n in r["doubles"]]
    lines += [f"   false alarm   {n} at {t:.1f} s" for n, t in r["false"]]
    return "\n".join(lines)


def load_all(folder, label) -> list:
    """[(file name, recording)] for one label, oldest first."""
    return [(f"{label}/{p.name}", gesture_recorder.load(p)) for p in sorted((Path(folder) / label).glob("*.json"))]


def main(argv) -> None:
    gesture_recs, not_recs = load_all(FOLDER, GESTURE), load_all(FOLDER, NOT)
    if not gesture_recs and not not_recs:
        print(f"No recordings in {FOLDER} yet. Run FIVES and use Ctrl+Option+F (flick) / Ctrl+Option+N (not).")
        return
    fps = [rec["fps"] for _, rec in gesture_recs + not_recs if rec.get("fps")]
    print(f"{len(gesture_recs)} '{GESTURE}' recordings, {len(not_recs)} '{NOT}' recordings, "
          f"recorded at about {statistics.median(fps):.0f} fps" if fps else "")
    known = detectors()
    wanted = argv or list(known)
    for name in wanted:
        if name not in known:
            print(f"\nNo detector called '{name}'. Choose from: {', '.join(known)}")
            continue
        about, make, should_fire = known[name]
        print(report(name, about, score(make, gesture_recs, not_recs), should_fire))


if __name__ == "__main__":
    main(sys.argv[1:])
