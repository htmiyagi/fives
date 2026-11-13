"""
wheel_logic.py - the wheel's math and rules, with no windows or AppKit, so it can be tested on its own.

The wheel (wheel.py) is FIVES's control room: one wedge per FIVES window, arranged in a ring.

                 wedge 0 (top)
            ╭─────────╮
     wedge 4│    ●    │wedge 1           wedges go clockwise from the top,
            │         │                  in the order saved in settings ("wheel_order")
     wedge 3╰─────────╯wedge 2

Three jobs live here:
  1. the ORDER: which windows are on the wheel, cleaned up so the rules always hold
  2. the GEOMETRY: which wedge a point is over, and where each wedge's middle is
  3. the HOVER GROWTH: how much each wedge grows (like the macOS Dock's magnification)
"""

import math

# Every FIVES window the wheel knows about: name -> the label that pops up on hover.
# (A new window = one line here, plus how to show it in actions.py.)
WINDOWS = {
    "music": "MUSIC",
    "sketch": "SKETCH",
    "brain": "BRAIN",
    "eyes": "EYES",
    "settings": "SETTINGS",
}

HUB_TABS = ("brain", "eyes", "settings")   # these are tabs in the FIVES window (hub.py), not windows of their own

DEFAULT_ORDER = ["music", "sketch", "brain", "eyes", "settings"]   # what FIVES ships with (friends start here)
MAX_WEDGES = 8                 # more than this makes the wedges too small to hit by hand
MUST_KEEP = "settings"         # can be moved but never removed (otherwise there's no way back to Settings)

HOVER_GROW = 0.14              # the hovered wedge's ring reaches this much further out (0.14 = 14%)
NEIGHBOR_GROW = 0.05           # the wedges right next to it grow a little too, so it feels like the Dock


# ---------------------------------------------------------------------------
# 1. The order
# ---------------------------------------------------------------------------
def clean_order(order) -> list[str]:
    """Turn whatever is saved (maybe old, maybe hand-edited) into an order that follows the rules:
    only known windows, no repeats, at most MAX_WEDGES, Settings always there, and at least one other wedge.
    Returns a NEW list; the one passed in is never changed."""
    if not isinstance(order, (list, tuple)):
        return list(DEFAULT_ORDER)
    seen = []
    for name in order:
        if name in WINDOWS and name not in seen:
            seen.append(name)
    if MUST_KEEP not in seen:
        seen = seen[:MAX_WEDGES - 1] + [MUST_KEEP]       # make room for Settings at the end
    if len(seen) > MAX_WEDGES:
        others = [n for n in seen if n != MUST_KEEP][:MAX_WEDGES - 1]
        seen = [n for n in seen if n in others or n == MUST_KEEP]   # keep Settings where it was
    if len(seen) < 2:                                    # only Settings left: start over from the default
        return list(DEFAULT_ORDER)
    return seen


# The WHEEL page in Settings (hub.py) edits the order with these. Each returns a NEW list, and asking for
# something the rules don't allow (remove Settings, add a 9th wedge) just gives the same order back.
def move(order, old_index: int, new_index: int) -> list[str]:
    """Take the wedge at old_index out and put it back at new_index (clamped to the list)."""
    out = list(order)
    name = out.pop(old_index)
    out.insert(max(0, min(new_index, len(out))), name)
    return out


def can_remove(order, name: str) -> bool:
    """Settings never comes off, and there's always at least one other wedge."""
    return name in order and name != MUST_KEEP and len(order) > 2


def remove(order, name: str) -> list[str]:
    return [n for n in order if n != name] if can_remove(order, name) else list(order)


def missing(order) -> list[str]:
    """The windows that aren't on the wheel right now (the [+] list), in the default order."""
    return [name for name in WINDOWS if name not in order]


def can_add(order) -> bool:
    return len(order) < MAX_WEDGES


def add(order, name: str) -> list[str]:
    """Put a window back on the wheel: just before Settings if Settings is last (so Settings keeps being the
    last Option+number), otherwise at the end (so nobody else's Option+number shifts)."""
    if name not in WINDOWS or name in order or not can_add(order):
        return list(order)
    if order and order[-1] == MUST_KEEP:
        return list(order[:-1]) + [name, MUST_KEEP]
    return list(order) + [name]


# ---------------------------------------------------------------------------
# 2. Geometry. Angles are in degrees, measured clockwise from straight up (like a clock).
#    Points use screen-style coordinates: x to the right, y DOWN (a "flipped" view).
# ---------------------------------------------------------------------------
def wedge_size(count: int) -> float:
    """How many degrees one wedge takes up."""
    return 360.0 / count


def wedge_middle(index: int, count: int) -> float:
    """The angle of the middle of a wedge. Wedge 0 is centred straight up."""
    return index * wedge_size(count)


def angle_of(x: float, y: float, cx: float, cy: float) -> float:
    """The clock angle of point (x, y) seen from the centre (cx, cy): 0 = up, 90 = right, 180 = down."""
    return math.degrees(math.atan2(x - cx, cy - y)) % 360.0    # atan2(right, up) gives the clock angle


def wedge_at(x, y, cx, cy, inner: float, outer: float, count: int):
    """Which wedge (0, 1, 2...) the point is over, or None if it's in the middle hole or outside the ring."""
    if count < 1:
        return None
    distance = math.hypot(x - cx, y - cy)
    if distance < inner or distance > outer:
        return None
    half = wedge_size(count) / 2
    return int(((angle_of(x, y, cx, cy) + half) % 360.0) // wedge_size(count))   # shift by half so wedge 0 is centred on "up"


def point_at(angle: float, radius: float, cx: float, cy: float) -> tuple[float, float]:
    """The point at a clock angle and distance from the centre (y down)."""
    a = math.radians(angle)
    return cx + radius * math.sin(a), cy - radius * math.cos(a)


def wedge_for_number(number: int, order) -> str | None:
    """Option+number: which window is in that spot of the wheel (1 = the first wedge), or None."""
    return order[number - 1] if 1 <= number <= len(order) else None


# ---------------------------------------------------------------------------
# 3. Hover growth
# ---------------------------------------------------------------------------
def growth(index: int, hovered, count: int) -> float:
    """How much bigger wedge `index` is drawn: 1.0 = normal. The hovered wedge grows most, its two
    neighbours a little (they wrap around: the last wedge is next to the first)."""
    if hovered is None or count < 1:
        return 1.0
    steps_away = min((index - hovered) % count, (hovered - index) % count)
    if steps_away == 0:
        return 1.0 + HOVER_GROW
    if steps_away == 1 and count > 2:
        return 1.0 + NEIGHBOR_GROW
    return 1.0
