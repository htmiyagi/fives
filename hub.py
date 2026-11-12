"""
hub.py - the FIVES window: ONE window with big tabs, like a browser. Everything lives in here now.

     FIVES   ( 01 EYES )  ( 02 BRAIN )  ( 03 SETTINGS )                       ● EYES ON   (x)
    +---------------------------------------------------------------------------------------+
    |                                                                                       |
    |      the tab you picked                                                               |
    |                                                                                       |
    +---------------------------------------------------------------------------------------+

  EYES      the hand-tracking picture, exactly as eyes.py draws it. eyes.py still does ALL the work, as its own
            program in the background. This tab only shows its picture (eyes_link.py carries it across).
            The same keys as before work while this tab is showing:
                c = hand control on/off    m = music window    h = view    t = hologram    [ ] = tint
                l = cursor lead            q = quit FIVES
  BRAIN     the AI's home. For now: a glowing orb. It is bright when the local model is ready (the Ollama app
            is running and has the model from config.py), dim when it is asleep. Voice and chat come later.
  SETTINGS  everyday choices (default music app...), saved by settings.py. Just the layout for now:
            the choices are remembered, but nothing uses them yet.
            CONNECT SPOTIFY opens a walkthrough on this tab (the steps and sign-in live in spotify_connect.py).

Started by the ENGAGE button in launcher.py.   Run by hand:  python hub.py
Drag empty glass to move the window. Drag the three dots in the bottom-right corner to resize it.
The round X closes FIVES (hand tracking stops too).

The look is a blend: the launcher's dark see-through glass, cut corners and faint grid, with round tabs,
circles and soft glows on top. Blues only.
The EYES picture itself is not restyled. Colours and sizes are at the top: tweak freely.
"""

import json
import math
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import objc
from AppKit import (NSAffineTransform, NSAppearance, NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor,
                    NSEvent, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSGradient,
                    NSGraphicsContext, NSImage, NSKernAttributeName, NSMakeRect, NSScreen, NSShadow, NSString, NSTrackingArea, NSURL,
                    NSView, NSVisualEffectView, NSWindow, NSZeroRect)
from Foundation import NSData, NSObject, NSTimer
from AppKit import NSColorSpace
from PyObjCTools import AppHelper
from Quartz import (CGContextBeginTransparencyLayer, CGContextEndTransparencyLayer, CGContextSetBlendMode,
                    kCGBlendModeDestinationIn)   # Quartz comes with pyautogui, nothing new to install

import eyes_link
import settings
import spotify_connect as sp

HERE = Path(__file__).resolve().parent
try:
    import config
    MODEL = config.MODEL
except Exception:
    MODEL = "qwen3.6:35b"

# ---- look ------------------------------------------------------------------------------------------
W, H = 1000, 652                 # design size. The window can be resized; everything scales with it
MIN_W = 640
RADIUS = 12                      # how round the window's round corners are
CUT = 22                         # how much is sliced off its two cut corners (top-left, bottom-right)
GLASS_ALPHA = 0.50               # how solid the blue glass is. Lower = see more of what's behind (0.3 to 0.95)
GRID = 0.05                      # how visible the faint grid is. 0 = none
GLOW = 1.0                       # glow strength. 0 = off
REST_WHEN_HIDDEN = True          # stop fetching the eyes picture while the window is covered or minimized (saves battery)
SEA = (0.030, 0.105, 0.30)       # the glass: this blue at the top...
DEEP = (0.010, 0.035, 0.11)      # ...fading to this one at the bottom
BLUE = (0.16, 0.60, 1.0)         # the FIVES neon blue (same as the launcher and the music window)
SKY = (0.42, 0.76, 1.0)
PALE = (0.62, 0.86, 1.0)
WHITE = (0.90, 0.96, 1.0)
CORE = (0.97, 0.99, 1.0)         # the orb's hot centre
GREY = (0.50, 0.68, 0.88)
NAVY = (0.04, 0.17, 0.46)        # dark blue for drawing on a bright button

# ---- where everything sits (top-left origin, design units) -----------------------------------------
PAGE = (20, 84, 960, 540)        # the tab's page. 960 x 540 is 16:9, the shape of the eyes picture
TAB_ORDER = [("eyes", "EYES"), ("brain", "BRAIN"), ("settings", "SETTINGS")]
TABS = {name: (150 + i * 188, 14, 176, 56) for i, (name, _) in enumerate(TAB_ORDER)}
CLOSE = (W - 44, 42, 17)         # centre x, centre y, radius
GRIP = (W - 36, H - 36, 36, 36)
ROWS = [                         # the SETTINGS tab: (settings.py key, title, what it means)
    ("music_app", "DEFAULT MUSIC APP", "Which app \"play some music\" opens"),
    ("spotify", "SPOTIFY", ""),          # not a saved choice: a CONNECT button (see spotify_connect.py)
    ("play_order", "PLAY ORDER", "What \"play my playlist\" does if you don't say"),
    ("ask_first", "ASK ME FIRST", "Show me before anything is sent or deleted"),
    ("speak_replies", "TALK BACK", "Read answers out loud"),
]
ROW_X, ROW_Y, ROW_W, ROW_H, ROW_GAP = 56, 170, 888, 76, 12
CONFIG_BUTTON = (56, 556, 318, 40)
ROWS_BOTTOM = CONFIG_BUTTON[1] - 14     # the settings rows scroll inside ROW_Y..ROWS_BOTTOM
WHEEL_STEP = 12                         # how far one click of a mouse wheel scrolls
FADE = 26                               # how tall the soft fade is where rows scroll out of sight
RESTART = (W / 2 - 110, 452, 220, 48)
EYES_KEYS = "cmhtl[]"            # keys passed on to eyes.py while the EYES tab is showing (q is handled here)


class State:
    tab = "eyes"
    hover = None                 # name of the button under the pointer
    pressed = None
    mode = None                  # "move" / "resize" while dragging
    scale = 1.0                  # window size / design size
    dirty = True                 # something changed: redraw
    eyes = None                  # the running eyes.py
    frame = None                 # the newest eyes picture (NSImage)
    frame_size = (16, 9)         # its width and height in pixels
    brain = "checking"           # "ready" / "missing" (Ollama is on, model isn't downloaded) / "asleep" / "checking"
    quitting = False
    settings_scroll = 0.0        # how far the SETTINGS rows are scrolled down


S = State()
link = None                      # eyes_link.Viewer, made in main()
win = view = fx = None


# ---- eyes.py, running in the background ------------------------------------------------------------
def eyes_running():
    return S.eyes is not None and S.eyes.poll() is None


def start_eyes():
    S.frame = None
    link.forget()                        # a leftover picture from an earlier run doesn't count
    S.eyes = subprocess.Popen([sys.executable, str(HERE / "eyes.py")], cwd=HERE, env=link.env(),
                              stdin=subprocess.PIPE, text=True, bufsize=1)


def stop_eyes():
    """Hang up: eyes.py notices and shuts down tidily (lets go of the mouse, closes its windows, frees the camera)."""
    proc, S.eyes = S.eyes, None
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.stdin.close()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def eyes_status():
    """off = eyes.py isn't running.  waking = it is starting up, no picture yet.  on = pictures are coming."""
    if not eyes_running():
        return "off"
    return "on" if S.frame is not None else "waking"


def quit_fives(*_):
    if S.quitting:
        return
    S.quitting = True
    try:
        win.orderOut_(None)              # disappear at once; eyes.py may take a second to finish
    except Exception:
        pass
    sp.close()                           # stops a sign-in that is still waiting
    stop_eyes()
    link.close()
    NSApplication.sharedApplication().terminate_(None)


def brain_loop():
    """Every few seconds: is the Ollama app running, and does it have our model? (The orb shows the answer.)"""
    while True:
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.5) as reply:
                names = [m.get("name", "") for m in json.loads(reply.read()).get("models", [])]
            S.brain = "ready" if (MODEL in names or MODEL + ":latest" in names) else "missing"
        except Exception:
            S.brain = "asleep"
        time.sleep(4)


# ---- drawing helpers (same idea as launcher.py, plus round shapes) ---------------------------------
def font(size, bold=False):
    f = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size)
    return f or (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))


def color(c, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)


def mix(a, b, t):
    """A colour between a and b (t = 0 gives a, t = 1 gives b)."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def glow_on(radius, c=BLUE, alpha=0.9):
    NSGraphicsContext.saveGraphicsState()
    sh = NSShadow.alloc().init()
    sh.setShadowOffset_((0, 0))
    sh.setShadowBlurRadius_(radius * GLOW * S.scale)
    sh.setShadowColor_(color(c, min(1.0, alpha * GLOW)))
    sh.set()


def glow_off():
    NSGraphicsContext.restoreGraphicsState()


def attrs(size, c=None, bold=False, kern=1.5, alpha=1.0):
    a = {NSFontAttributeName: font(size, bold), NSKernAttributeName: kern}
    if c is not None:
        a[NSForegroundColorAttributeName] = color(c, alpha)
    return a


def text(s, x, y, size, c, bold=False, kern=1.5, alpha=1.0, glow=0, glow_color=BLUE):
    if glow:
        glow_on(glow, glow_color)
    NSString.stringWithString_(s).drawAtPoint_withAttributes_((x, y), attrs(size, c, bold, kern, alpha))
    if glow:
        glow_off()


def text_width(s, size, bold=False, kern=1.5):
    return NSString.stringWithString_(s).sizeWithAttributes_(attrs(size, None, bold, kern)).width


def text_mid(s, cx, y, size, c, bold=False, kern=1.5, alpha=1.0, glow=0):
    """Text centred on cx."""
    text(s, cx - (text_width(s, size, bold, kern) - kern) / 2, y, size, c, bold, kern, alpha, glow)


def path(points, k=1.0, closed=True):
    p = NSBezierPath.bezierPath()
    for i, (x, y) in enumerate(points):
        (p.moveToPoint_ if i == 0 else p.lineToPoint_)((x * k, y * k))
    if closed:
        p.closePath()
    return p


def paint(p, fill=None, fill_alpha=1.0, stroke=None, width=1.0, stroke_alpha=1.0, glow=0, glow_color=BLUE):
    """Fill and/or outline a shape, with an optional glow."""
    if glow:
        glow_on(glow, glow_color)
    if fill is not None:
        color(fill, fill_alpha).set()
        p.fill()
    if stroke is not None:
        color(stroke, stroke_alpha).set()
        p.setLineWidth_(width)
        p.stroke()
    if glow:
        glow_off()


def rounded(rect, r, steps=7, cut=""):
    """The outline of a rectangle with round corners, as points. r = half the height makes a pill.
    r can be four numbers, one per corner: (top-right, bottom-right, bottom-left, top-left).
    cut names corners to slice off straight instead of rounding: "tl br" = top-left and bottom-right."""
    x, y, w, h = rect
    sizes = [min(v, w / 2, h / 2) for v in (r if isinstance(r, (tuple, list)) else (r, r, r, r))]
    corners = (("tr", x + w, y, -1, 1, -90), ("br", x + w, y + h, -1, -1, 0),
               ("bl", x, y + h, 1, -1, 90), ("tl", x, y, 1, 1, 180))
    pts = []
    for (name, px, py, sx, sy, start), size in zip(corners, sizes):
        cx, cy = px + sx * size, py + sy * size          # the centre of this corner's curve
        n = 1 if name in cut else steps                  # a cut corner is one straight step
        for i in range(n + 1):
            a = math.radians(start + 90 * i / n)
            pts.append((cx + size * math.cos(a), cy + size * math.sin(a)))
    return pts


def pill(rect, r=None, cut="", **look):
    paint(path(rounded(rect, rect[3] / 2 if r is None else r, cut=cut)), **look)


def plate(rect, **look):
    """A button shaped like the launcher's: top-left and bottom-right corners sliced off."""
    pill(rect, (3, 9, 3, 9), "tl br", **look)


def oval(cx, cy, rx, ry=None, **look):
    ry = rx if ry is None else ry
    paint(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - rx, cy - ry, 2 * rx, 2 * ry)), **look)


def stroke(points, c, width=1.0, alpha=1.0, glow=0):
    """A line through the points, with round ends."""
    p = path(points, closed=False)
    p.setLineCapStyle_(1)
    p.setLineJoinStyle_(1)
    paint(p, stroke=c, width=width, stroke_alpha=alpha, glow=glow)


def ellipse(cx, cy, rx, ry, tilt=0.0, a0=0.0, a1=360.0, n=48):
    """Points along a (tilted) ellipse from angle a0 to a1, in degrees. 180..360 is the far side."""
    t = math.radians(tilt)
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + ex * math.cos(t) - ey * math.sin(t), cy + ex * math.sin(t) + ey * math.cos(t)))
    return out


def inside(p, rect):
    return rect[0] <= p[0] <= rect[0] + rect[2] and rect[1] <= p[1] <= rect[1] + rect[3]


# ---- small pictures (icons) -------------------------------------------------------------------------
def icon(name, cx, cy, c):
    if name == "eyes":                                   # a lens
        oval(cx, cy, 9, stroke=c, width=2.0)
        oval(cx, cy, 3.6, fill=c)
    elif name == "brain":                                # a little planet with a ring
        stroke(ellipse(cx, cy, 12, 4.6, -24, 200, 340, 12), c, 1.6, 0.7)
        oval(cx, cy, 5.5, fill=c)
        stroke(ellipse(cx, cy, 12, 4.6, -24, -20, 200, 16), c, 1.6)
    elif name == "settings":                             # two sliders
        for dy, knob in ((-5, 4), (5, -4)):
            stroke([(cx - 9, cy + dy), (cx + 9, cy + dy)], c, 2.0)
            oval(cx + knob, cy + dy, 3.6, fill=c)
    elif name == "music_app":                            # a note
        oval(cx - 4, cy + 8, 5.5, 4.5, fill=c)
        stroke([(cx + 1, cy + 8), (cx + 1, cy - 11), (cx + 10, cy - 7)], c, 2.2)
    elif name == "play_order":                           # shuffle: two crossing arrows
        stroke([(cx - 10, cy - 6), (cx + 10, cy + 6)], c, 2.2)
        stroke([(cx - 10, cy + 6), (cx + 10, cy - 6)], c, 2.2)
        stroke([(cx + 5, cy + 7), (cx + 10, cy + 6), (cx + 8, cy + 1)], c, 2.0)
        stroke([(cx + 5, cy - 7), (cx + 10, cy - 6), (cx + 8, cy - 1)], c, 2.0)
    elif name == "ask_first":                            # a hand-up "wait": a ring with a check
        stroke([(cx - 8, cy + 1), (cx - 2, cy + 7), (cx + 9, cy - 7)], c, 2.4)
    elif name == "spotify":                              # three sound waves
        for k, (rx, ry) in enumerate(((13, 5.5), (10, 4.5), (7, 3.5))):
            stroke(ellipse(cx, cy - 6 + k * 7 + ry, rx, ry, 0, 200, 340, 12), c, 2.4 - k * 0.3)
    elif name == "speak_replies":                        # sound bars
        for dx, half in ((-9, 5), (-3, 11), (3, 7), (9, 3)):
            stroke([(cx + dx, cy - half), (cx + dx, cy + half)], c, 2.4)


# ---- the three tabs' pages --------------------------------------------------------------------------
def page(fill=BLUE, alpha=0.07):
    pill(PAGE, (8, 20, 8, 8), "br", fill=fill, fill_alpha=alpha, stroke=SKY, width=1.0, stroke_alpha=0.25)


def draw_eyes():
    x, y, w, h = PAGE
    status = eyes_status()
    if S.frame is not None and status != "off":
        fw, fh = S.frame_size
        k = min(w / fw, h / fh)                          # as big as fits, never stretched
        spot = (x + (w - fw * k) / 2, y + (h - fh * k) / 2, fw * k, fh * k)
        if spot[2] < w - 1 or spot[3] < h - 1:           # a picture that isn't 16:9 gets a dark page around it
            page(DEEP, 0.55)
        NSGraphicsContext.saveGraphicsState()
        path(rounded(spot, 6)).addClip()                 # only the very corners are rounded off
        # respectFlipped: our view counts y from the top, so the picture must not draw upside down
        S.frame.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            NSMakeRect(*spot), NSZeroRect, 2, 1.0, True, None)
        NSGraphicsContext.restoreGraphicsState()
        pill(spot, 6, stroke=BLUE, width=1.0, stroke_alpha=0.45)
        return
    page(DEEP, 0.55)
    cx, cy = x + w / 2, y + h / 2 - 30
    if status == "waking":
        spin = (time.time() * 300) % 360
        oval(cx, cy, 30, stroke=BLUE, width=4, stroke_alpha=0.22)
        stroke(ellipse(cx, cy, 30, 30, 0, spin, spin + 100, 16), SKY, 4, 1.0, glow=8)
        text_mid("WAKING UP THE CAMERA", cx, cy + 58, 18, WHITE, True, 4.0)
        text_mid("this takes a few seconds", cx, cy + 86, 13, PALE, False, 1.0, 0.85)
    else:
        oval(cx, cy, 30, stroke=GREY, width=3, stroke_alpha=0.6)
        stroke([(cx - 12, cy), (cx + 12, cy)], GREY, 3, 0.8)
        text_mid("EYES ARE OFF", cx, cy + 58, 18, WHITE, True, 4.0)
        text_mid("hand tracking stopped. If that was a surprise, the Terminal says why.", cx, cy + 86, 13, PALE, False, 1.0, 0.85)
        hov = S.hover == "restart"
        plate(RESTART, fill=BLUE, fill_alpha=0.75 if hov else 0.50, stroke=WHITE if hov else SKY, width=1.3,
              stroke_alpha=0.95, glow=10 if hov else 5)
        text_mid("START EYES", RESTART[0] + RESTART[2] / 2, RESTART[1] + 13, 16, WHITE, True, 3.5)


def draw_brain():
    page()
    x, y, w, h = PAGE
    now = time.time()
    awake = S.brain == "ready"
    power = 1.0 if awake else 0.42                       # how brightly it shines
    breath = 0.5 + 0.5 * math.sin(now * (1.7 if awake else 0.8))
    cx, cy, r = x + w / 2, y + 214, 66 * (1 + 0.03 * breath)
    ty = cy + 168                                        # the round table it floats over

    # the table: rings of light, like a command-centre projector
    oval(cx, ty, 226, 38, fill=BLUE, fill_alpha=0.10 * power + 0.03)
    oval(cx, ty, 226, 38, stroke=BLUE, width=1.6, stroke_alpha=0.85 * power + 0.1, glow=10)
    oval(cx, ty, 176, 29, stroke=SKY, width=1.0, stroke_alpha=0.45)
    oval(cx, ty, 112, 18, fill=SKY, fill_alpha=0.10 + 0.10 * power * breath)
    paint(path([(cx - 112, ty), (cx + 112, ty), (cx + 46, cy + r), (cx - 46, cy + r)]),
          fill=SKY, fill_alpha=0.05 * power)            # a faint beam up to the orb

    # two orbits with a little moon each: the far half is drawn first so the orb covers it
    orbits = [(172, 50, -16, now * 38), (128, 30, 22, -now * 55 + 120)]
    for rx, ry, tilt, at in orbits:
        stroke(ellipse(cx, cy, rx, ry, tilt, 180, 360), SKY, 1.3, 0.30 * power + 0.12)
    moons = [(ellipse(cx, cy, rx, ry, tilt, at % 360, at % 360, 1)[0], math.sin(math.radians(at)) < 0)
             for rx, ry, tilt, at in orbits]
    for (mx, my), behind in moons:
        if behind:
            oval(mx, my, 4.5, fill=PALE, fill_alpha=0.7 * power + 0.2)

    # the orb: a soft halo, then circles shrinking from blue at the edge to white-hot in the middle
    for i in range(16, 0, -1):
        f = i / 16
        oval(cx, cy, r * (1 + 1.7 * f), fill=BLUE, fill_alpha=(0.030 + 0.016 * breath) * power * (1 - f) + 0.003)
    oval(cx, cy, r, fill=BLUE, fill_alpha=0.95, glow=34 * power + 6, glow_color=BLUE)
    steps = 30
    for i in range(steps):
        f = i / (steps - 1)                              # 0 = the edge, 1 = the centre
        shade = mix(mix(BLUE, DEEP, 0.25 * (1 - power)), CORE, (f ** 0.85) * (0.55 + 0.45 * power))
        oval(cx - r * 0.16 * f, cy - r * 0.20 * f, r * (1 - 0.90 * f), fill=shade)
    oval(cx, cy, r, stroke=PALE, width=1.2, stroke_alpha=0.55)

    for rx, ry, tilt, at in orbits:                      # the near halves, in front of the orb
        stroke(ellipse(cx, cy, rx, ry, tilt, 0, 180), SKY, 1.6, 0.55 * power + 0.2, glow=5)
    for (mx, my), behind in moons:
        if not behind:
            oval(mx, my, 5.5, fill=CORE, glow=10)

    words = {"ready": "AWAKE", "missing": "NOT DOWNLOADED YET", "asleep": "ASLEEP", "checking": "CHECKING"}[S.brain]
    more = {"ready": "voice and chat will live here",
            "missing": "in Terminal:  ollama pull " + MODEL,
            "asleep": "open the Ollama app to wake it",
            "checking": ""}[S.brain]
    text_mid(MODEL.upper(), cx, ty + 62, 20, WHITE, True, 5.0, glow=6 if awake else 0)
    dot_w = text_width(words, 12, True, 3.5)
    oval(cx - dot_w / 2 - 11, ty + 99, 4, fill=SKY if awake else GREY, glow=6 if awake else 0)
    text_mid(words, cx + 4, ty + 91, 12, SKY if awake else GREY, True, 3.5)
    text_mid(more, cx, ty + 111, 12, PALE, False, 1.0, 0.7)


def row_rect(i):
    return (ROW_X, ROW_Y + i * (ROW_H + ROW_GAP) - S.settings_scroll, ROW_W, ROW_H)


def max_scroll():
    """How far the rows can scroll: 0 when they all fit."""
    bottom = ROW_Y + len(ROWS) * (ROW_H + ROW_GAP) - ROW_GAP
    return max(0.0, bottom - ROWS_BOTTOM)


def scroll_settings(dy):
    """Move the rows by dy (positive = further down the list), never past either end."""
    S.settings_scroll = min(max(S.settings_scroll + dy, 0.0), max_scroll())
    S.dirty = True


def can_see(rect):
    """Is a button's middle inside the scrolling area? (Hidden rows can't be clicked.)"""
    middle = rect[1] + rect[3] / 2
    return ROW_Y <= middle <= ROWS_BOTTOM


def choice_rects(i, key):
    """Where each option of a pick-one row sits (a pill cut into equal parts)."""
    x, y, w, h = row_rect(i)
    options = settings.CHOICES[key]
    each = 150
    left = x + w - 24 - each * len(options)
    return [(option, (left + n * each, y + (h - 44) / 2, each, 44)) for n, option in enumerate(options)]


def toggle_rect(i):
    x, y, w, h = row_rect(i)
    return (x + w - 24 - 78, y + (h - 40) / 2, 78, 40)


def connect_rect(i):
    x, y, w, h = row_rect(i)
    return (x + w - 24 - 170, y + (h - 40) / 2, 170, 40)


def wrap(s, size, width, bold=False, kern=0.8):
    """Break a sentence into lines that fit in `width`."""
    lines, line = [], ""
    for word in s.split():
        trial = (line + " " + word).strip()
        if line and text_width(trial, size, bold, kern) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def spotify_buttons():
    """The walkthrough's buttons for the step it is on: (name, rectangle, label, is it the main one)."""
    step = sp.setup.step
    main = (W - 56 - 300, 550, 300, 50)
    out = [("sp:cancel", (56, 556, 130, 44), "CLOSE", False)]
    if step in ("basic", "create", "client_id", "signin", "waiting", "error"):
        out.append(("sp:back", (198, 556, 130, 44), "BACK", False))
    if step == "premium":
        out += [("sp:no", (80, 414, 384, 46), "NO PREMIUM", False), ("sp:yes", (536, 414, 384, 46), "YES, I HAVE PREMIUM", True)]
    elif step == "create":
        out += [("sp:open", (W - 56 - 290, 172, 290, 42), "OPEN SPOTIFY DEVELOPER", True),
                ("sp:copy", (W - 56 - 130, 340, 130, 42), "COPIED" if time.time() - sp.setup.copied_at < 1.5 else "COPY", True),
                ("sp:next", main, "NEXT: I SAVED IT", True)]
    elif step == "signin":
        out.append(("sp:signin", main, "SIGN IN WITH SPOTIFY", True))
    elif step in ("basic", "done"):
        out.append(("sp:finish", main, "DONE", True))
    elif step == "error":
        out.append(("sp:retry", main, "TRY AGAIN", True))
    return out


def spinner(cx, cy, r=22):
    spin = (time.time() * 300) % 360
    oval(cx, cy, r, stroke=BLUE, width=4, stroke_alpha=0.22)
    stroke(ellipse(cx, cy, r, r, 0, spin, spin + 100, 16), SKY, 4, 1.0, glow=8)


def badge(cx, cy, mark):
    """A ring with a tick or an exclamation mark in it."""
    oval(cx, cy, 30, fill=NAVY, fill_alpha=0.55, stroke=SKY, width=2.4, stroke_alpha=0.95, glow=8)
    if mark == "tick":
        stroke([(cx - 11, cy + 1), (cx - 3, cy + 9), (cx + 12, cy - 9)], WHITE, 3.2)
    else:
        stroke([(cx, cy - 12), (cx, cy + 3)], WHITE, 3.2)
        oval(cx, cy + 11, 2.2, fill=WHITE)


def paragraph(s, x, y, width, size=15, c=PALE, alpha=0.95):
    """Wrapped text. Returns the y just below it."""
    for line in wrap(s, size, width):
        text(line, x, y, size, c, False, 0.8, alpha)
        y += size * 1.45
    return y


def draw_spotify():
    """The CONNECT SPOTIFY walkthrough. What happens on each button press is in spotify_connect.press()."""
    page()
    step, st = sp.setup.step, sp.setup
    text("CONNECT SPOTIFY", 58, 104, 26, WHITE, True, 6.0, glow=6)
    at = sp.STEP_NUMBER.get(step, 5 if step == "done" else 0)
    if at:                                               # four dots: where you are in the steps
        for n in range(1, 5):
            cx, cy = 764 + (n - 1) * 52, 122
            if n < 4:
                stroke([(cx + 18, cy), (cx + 34, cy)], SKY if n < at else GREY, 1.4, 0.7)
            oval(cx, cy, 14, fill=BLUE if n <= at else NAVY, fill_alpha=0.85 if n == at else 0.35,
                 stroke=WHITE if n == at else SKY if n < at else GREY, width=1.4, glow=8 if n == at else 0)
            text_mid(str(n), cx, cy - 9, 14, WHITE if n <= at else GREY, True, 0.0)

    if step == "premium":
        text("DO YOU HAVE SPOTIFY PREMIUM?", 58, 164, 20, WHITE, True, 3.0)
        cards = [(56, "WITHOUT PREMIUM", "works right now, nothing to set up",
                  ["play, pause, skip", "shuffle on and off", "what's playing"]),
                 (512, "WITH PREMIUM", "one-time setup, about 3 minutes",
                  ["everything on the left", "find and play any song", "your playlists by name", "make new playlists"])]
        for x, title, note, lines in cards:
            best = title == "WITH PREMIUM"
            pill((x, 206, 432, 270), (10, 20, 10, 10), "br", fill=BLUE, fill_alpha=0.14 if best else 0.07,
                 stroke=SKY, width=1.2 if best else 1.0, stroke_alpha=0.6 if best else 0.3)
            text(title, x + 24, 220, 18, WHITE, True, 3.0)
            text(note, x + 25, 247, 13, GREY, False, 0.8)
            for k, line in enumerate(lines):
                oval(x + 31, 290 + k * 27, 3.2, fill=SKY)
                text(line, x + 46, 279 + k * 27, 15, PALE, False, 0.8)
    elif step == "basic":
        badge(W / 2, 220, "tick")
        text_mid("YOU'RE ALL SET", W / 2, 272, 20, WHITE, True, 4.0)
        text_mid("Play, pause, skip and shuffle work through the Spotify app with no setup.", W / 2, 312, 15, PALE, False, 0.8)
        text_mid("If you get Premium later, come back here to unlock search and playlists.", W / 2, 336, 15, PALE, False, 0.8)
    elif step == "create":
        items = [(178, "Press the button and log in with your Spotify account."),
                 (244, "Click \"Create app\". App name and description: anything, like FIVES."),
                 (310, "Redirect URI: paste this address, then click Add."),
                 (418, "Tick \"Web API\", agree to the terms, and click Save.")]
        for n, (y, line) in enumerate(items):
            oval(78, y + 14, 15, fill=NAVY, fill_alpha=0.55, stroke=SKY, width=1.5, stroke_alpha=0.9)
            text_mid(str(n + 1), 78, y + 4, 15, WHITE, True, 0.0)
            text(line, 110, y + 3, 16, WHITE, False, 0.8)
        pill((110, 340, W - 56 - 130 - 12 - 110, 42), 8, fill=DEEP, fill_alpha=0.6, stroke=BLUE, width=1.2, stroke_alpha=0.6)
        text(sp.REDIRECT, 126, 351, 16, SKY, True, 1.2)
        text("Spotify only lets Premium accounts create an app. The app is free.", 110, 462, 13, GREY, False, 0.8)
    elif step == "client_id":
        text("COPY YOUR CLIENT ID", 58, 164, 20, WHITE, True, 3.0)
        y = paragraph("Your new app's page in the browser shows a Client ID: a long code of letters and numbers. "
                      "Copy it (there is a copy button next to it).", 58, 204, 620)
        paragraph("FIVES is watching the clipboard and picks it up by itself.", 58, y + 8, 620)
        spinner(W / 2, 376)
        text_mid("WAITING FOR THE COPY", W / 2, 416, 13, SKY, True, 3.5)
    elif step == "signin":
        text("LAST STEP: SIGN IN", 58, 164, 20, WHITE, True, 3.0)
        oval(66, 221, 4, fill=SKY, glow=6)
        text(f"CLIENT ID RECEIVED   {st.client_id[:4]}...{st.client_id[-4:]}", 80, 212, 13, SKY, True, 2.5)
        y = paragraph("Press SIGN IN. Your browser opens Spotify's own page asking if FIVES may control your music: "
                      "click AGREE.", 58, 250, 640)
        paragraph("FIVES never sees your password. The key it gets is saved only on this Mac.", 58, y + 8, 640, 14, GREY)
    elif step == "waiting":
        spinner(W / 2, 250)
        text_mid("WAITING FOR YOU TO CLICK AGREE IN THE BROWSER", W / 2, 296, 14, SKY, True, 3.0)
        text_mid("If Spotify's page shows \"Invalid redirect URI\" or \"Invalid client\", press BACK and check",
                 W / 2, 344, 14, PALE, False, 0.8, 0.85)
        text_mid("the address in step 3, or copy the Client ID again.", W / 2, 366, 14, PALE, False, 0.8, 0.85)
    elif step == "done":
        badge(W / 2, 216, "tick")
        text_mid("CONNECTED", W / 2, 268, 22, WHITE, True, 5.0, glow=6)
        text_mid("as " + (st.name or "your account"), W / 2, 302, 16, SKY, False, 1.0)
        text_mid("Test search: it works." if st.search_ok else
                 "Signed in, but a test search didn't come back. Try CONNECT again later.", W / 2, 346, 15, PALE, False, 0.8)
        text_mid("Searching songs and playlists by voice comes with the music tools, next.", W / 2, 370, 15, PALE, False, 0.8, 0.8)
    elif step == "error":
        badge(W / 2, 216, "bang")
        text_mid("THAT DIDN'T WORK", W / 2, 268, 20, WHITE, True, 4.0)
        y = 310
        for line in wrap(st.error[:1].upper() + st.error[1:] + ".", 15, 700):
            text_mid(line, W / 2, y, 15, PALE, False, 0.8)
            y += 22

    for name, rect, label, main in spotify_buttons():
        hov = S.hover == name
        plate(rect, fill=BLUE, fill_alpha=(0.75 if hov else 0.50) if main else (0.30 if hov else 0.06),
              stroke=WHITE if hov else SKY, width=1.3, stroke_alpha=0.95 if (hov or main) else 0.5,
              glow=(10 if hov else 5) if main else 0)
        size = 15 if rect[3] >= 46 else 13
        text_mid(label, rect[0] + rect[2] / 2, rect[1] + (rect[3] - size * 1.28) / 2, size, WHITE if (hov or main) else PALE, True, 2.5)


def draw_settings():
    if sp.setup.step != "closed":
        return draw_spotify()
    page()
    text("SETTINGS", 58, 104, 26, WHITE, True, 6.0, glow=6)
    text("your choices are saved on this Mac", 60, 138, 13, PALE, False, 1.0, 0.8)
    NSGraphicsContext.saveGraphicsState()                   # rows only show inside the scrolling area
    NSBezierPath.clipRect_(NSMakeRect(0, ROW_Y - 10, W, ROWS_BOTTOM - ROW_Y + 10))
    CGContextBeginTransparencyLayer(NSGraphicsContext.currentContext().CGContext(), None)  # rows on their own layer
    for i, (key, title, about) in enumerate(ROWS):
        x, y, w, h = row_rect(i)
        pill((x, y, w, h), (10, 20, 10, 10), "br", fill=BLUE, fill_alpha=0.09, stroke=SKY, width=1.0, stroke_alpha=0.32)
        oval(x + 46, y + h / 2, 25, fill=NAVY, fill_alpha=0.55, stroke=SKY, width=1.6, stroke_alpha=0.9)
        icon(key, x + 46, y + h / 2, WHITE)
        if key == "spotify":
            name, hov = sp.who(), S.hover == "connect"
            about = (f"Connected as {name}: search and playlists are unlocked" if name else
                     "Basic controls work now. Connect (Premium) for search and playlists")
            rect = connect_rect(i)
            plate(rect, fill=BLUE, fill_alpha=(0.30 if hov else 0.06) if name else (0.75 if hov else 0.50),
                  stroke=WHITE if hov else SKY, width=1.3, stroke_alpha=0.95, glow=0 if name else (10 if hov else 5))
            text_mid("DISCONNECT" if name else "CONNECT", rect[0] + rect[2] / 2, rect[1] + 12, 13, WHITE, True, 2.5)
        text(title, x + 90, y + 13, 19, WHITE, True, 3.0)
        text(about, x + 91, y + 42, 14, PALE, False, 0.8, 0.9)
        if key == "spotify":
            continue
        if key in settings.CHOICES:
            rects = choice_rects(i, key)
            first, last = rects[0][1], rects[-1][1]
            pill((first[0], first[1], last[0] + last[2] - first[0], first[3]), 9,
                 fill=DEEP, fill_alpha=0.55, stroke=BLUE, width=1.2, stroke_alpha=0.6)
            for option, rect in rects:
                on, hov = settings.get(key) == option, S.hover == f"set:{key}:{option}"
                if on:
                    pill((rect[0] + 3, rect[1] + 3, rect[2] - 6, rect[3] - 6), 7, fill=BLUE, fill_alpha=0.80, glow=8)
                text_mid(option.upper(), rect[0] + rect[2] / 2, rect[1] + 13, 14,
                         WHITE if (on or hov) else GREY, True, 2.0)
        else:
            on, hov = bool(settings.get(key)), S.hover == f"toggle:{key}"
            tx, ty, tw, th = toggle_rect(i)
            text("ON" if on else "OFF", tx - 46, ty + 11, 14, SKY if on else GREY, True, 3.0)
            pill((tx, ty, tw, th), fill=BLUE if on else DEEP, fill_alpha=0.80 if on else 0.55,
                 stroke=WHITE if hov else BLUE, width=1.2, stroke_alpha=0.9 if hov else 0.6, glow=8 if on else 0)
            oval(tx + (tw - th / 2 if on else th / 2), ty + th / 2, th / 2 - 5, fill=CORE if on else GREY)
    fade_edges()
    CGContextEndTransparencyLayer(NSGraphicsContext.currentContext().CGContext())
    NSGraphicsContext.restoreGraphicsState()
    draw_scrollbar()
    hov = S.hover == "config"
    plate(CONFIG_BUTTON, fill=BLUE, fill_alpha=0.30 if hov else 0.06, stroke=WHITE if hov else SKY,
         width=1.2, stroke_alpha=0.9 if hov else 0.5)
    text_mid("HAND TRACKING SETTINGS FILE", CONFIG_BUTTON[0] + CONFIG_BUTTON[2] / 2, CONFIG_BUTTON[1] + 12, 13,
             WHITE if hov else PALE, True, 2.5)
    text("opens config.py: the numbers behind the hand tracking", CONFIG_BUTTON[0] + CONFIG_BUTTON[2] + 18,
         CONFIG_BUTTON[1] + 12, 13, GREY, False, 0.8, 0.85)


def fade_edges():
    """Softly fade the rows where they scroll out of sight. "Destination in" keeps what's already drawn only as
    much as the gradient is solid: like an eraser that rubs harder near the edge. Only fades an edge that has
    more rows past it, so the list looks normal when it's all the way up or down."""
    top, bottom = ROW_Y - 10, ROWS_BOTTOM
    height = bottom - top
    edge = FADE / height                                       # the fade's size, as a fraction of the area
    fade_top, fade_bottom = S.settings_scroll > 0, S.settings_scroll < max_scroll()
    colors = [NSColor.colorWithWhite_alpha_(1, 0 if fade_top else 1), NSColor.colorWithWhite_alpha_(1, 1),
              NSColor.colorWithWhite_alpha_(1, 1), NSColor.colorWithWhite_alpha_(1, 0 if fade_bottom else 1)]
    mask = NSGradient.alloc().initWithColors_atLocations_colorSpace_(colors, (0.0, edge, 1 - edge, 1.0),
                                                             NSColorSpace.sRGBColorSpace())
    CGContextSetBlendMode(NSGraphicsContext.currentContext().CGContext(), kCGBlendModeDestinationIn)
    mask.drawInRect_angle_(NSMakeRect(0, top, W, height), 90)


def draw_scrollbar():
    """A thin bar right of the rows, so you can tell there's more below. Hidden when everything fits."""
    if max_scroll() <= 0:
        return
    x, top, height = ROW_X + ROW_W + 8, ROW_Y, ROWS_BOTTOM - ROW_Y
    shown = height / (height + max_scroll())               # how much of the list fits on screen
    bar = height * shown
    y = top + (height - bar) * S.settings_scroll / max_scroll()
    pill((x, top, 4, height), 2, fill=SKY, fill_alpha=0.12)
    pill((x, y, 4, bar), 2, fill=SKY, fill_alpha=0.75, glow=6)


# ---- the whole window -------------------------------------------------------------------------------
def frame_points(inset=0.0):
    """The window's outline: two round corners, two cut ones (like the launcher's armor)."""
    return rounded((inset, inset, W - 2 * inset, H - 2 * inset), (RADIUS, CUT, RADIUS, CUT), 8, "tl br")


def draw():
    # blue glass: brighter at the top, deeper at the bottom, with two big soft circles
    try:
        fade = NSGradient.alloc().initWithStartingColor_endingColor_(color(SEA, GLASS_ALPHA), color(DEEP, GLASS_ALPHA))
        fade.drawFromPoint_toPoint_options_((0, 0), (0, H), 3)
    except Exception:                       # no fade available: one flat blue
        color(mix(SEA, DEEP, 0.5), GLASS_ALPHA).set()
        NSBezierPath.fillRect_(NSMakeRect(0, 0, W, H))
    oval(W - 150, 30, 250, fill=SKY, fill_alpha=0.028)
    oval(120, H + 60, 230, fill=BLUE, fill_alpha=0.04)
    if GRID:
        for gx in range(0, W + 1, 24):
            stroke([(gx, 0), (gx, H)], BLUE, 0.5, GRID)
        for gy in range(0, H + 1, 24):
            stroke([(0, gy), (W, gy)], BLUE, 0.5, GRID)
    # frame: a glowing outline, a thin inner one, bright armor edges on the cut corners, a tick ruler
    paint(path(frame_points(1)), stroke=BLUE, width=1.7, stroke_alpha=0.9, glow=9)
    paint(path(frame_points(6)), stroke=BLUE, width=0.8, stroke_alpha=0.35)
    stroke([(CUT, 1), (1, CUT)], WHITE, 2.6, 0.95, glow=7)
    stroke([(W - CUT, H - 1), (W - 1, H - CUT)], WHITE, 2.6, 0.95, glow=7)
    for tx in range(716, 860, 8):
        stroke([(tx, 2), (tx, 5 if (tx // 8) % 5 else 9)], WHITE, 1.0, 0.5)

    # top strip: name, fat tabs, status, close
    text("FIVES", 28, 22, 30, WHITE, True, 6.0, glow=8)
    for k, (name, label) in enumerate(TAB_ORDER):
        x, y, w, h = TABS[name]
        on, hov = S.tab == name, S.hover == "tab:" + name
        shape = dict(r=(18, 6, h / 2, h / 2), cut="tr")     # round where the icon sits, sliced at the far corner
        if on:
            pill((x, y, w, h), fill=BLUE, fill_alpha=0.72, stroke=PALE, width=1.3, stroke_alpha=0.95, glow=13, **shape)
        else:
            pill((x, y, w, h), fill=BLUE if hov else DEEP, fill_alpha=0.28 if hov else 0.40,
                 stroke=WHITE if hov else BLUE, width=1.3, stroke_alpha=0.9 if hov else 0.6, **shape)
        bx, by = x + h / 2, y + h / 2
        if on:
            oval(bx, by, 20, fill=CORE)
        else:
            oval(bx, by, 20, fill=NAVY, fill_alpha=0.5, stroke=SKY, width=1.4, stroke_alpha=0.75)
        icon(name, bx, by, NAVY if on else PALE)
        text(f"0{k + 1}", x + h + 1, y + 8, 11, WHITE if on else GREY, True, 2.5, 0.8)
        text(label, x + h, y + 19, 21, WHITE if on else PALE, True, 3.0)

    status = eyes_status()
    word = {"on": "EYES ON", "waking": "WAKING UP", "off": "EYES OFF"}[status]
    sw = text_width(word, 13, True, 3.0)
    sx = W - 78 - sw
    if status == "on":
        pulse = 0.55 + 0.45 * abs(((time.time() * 1.2) % 2) - 1)
        oval(sx - 13, 42, 4.5, fill=SKY, fill_alpha=pulse, glow=8)
    else:
        oval(sx - 13, 42, 4.5, stroke=GREY, width=1.4, stroke_alpha=0.9)
    text(word, sx, 33, 13, SKY if status == "on" else GREY, True, 3.0)
    cx, cy, cr = CLOSE
    hov = S.hover == "close"
    oval(cx, cy, cr, fill=BLUE, fill_alpha=0.45 if hov else 0.12, stroke=WHITE if hov else SKY, width=1.4,
         stroke_alpha=0.95 if hov else 0.6, glow=6 if hov else 0)
    for dx in (-1, 1):
        stroke([(cx - 5.5 * dx, cy - 5.5), (cx + 5.5 * dx, cy + 5.5)], WHITE if hov else PALE, 2.0)

    {"eyes": draw_eyes, "brain": draw_brain, "settings": draw_settings}[S.tab]()

    # bottom strip: a hint for this tab, and the resize dots
    text("FIVES  //  HOME", 28, H - 22, 10, GREY, False, 3.0, 0.7)
    hint = {"eyes": "C  HAND CONTROL      M  MUSIC      H  VIEW      Q  QUIT",
            "brain": "THE ORB IS BRIGHT WHEN THE LOCAL MODEL IS READY",
            "settings": "CLICK OR PINCH TO CHANGE"}[S.tab]
    text(hint, W - 52 - text_width(hint, 10, False, 2.5), H - 22, 10, GREY, False, 2.5, 0.8)
    for dx, dy in ((0, 0), (-9, 0), (0, -9)):
        oval(W - 16 + dx, H - 16 + dy, 2.2, fill=WHITE if S.hover == "grip" else SKY, fill_alpha=0.9)


# ---- clicks and keys --------------------------------------------------------------------------------
def buttons():
    """Everything you can click right now: (name, rectangle)."""
    out = [("tab:" + name, TABS[name]) for name, _ in TAB_ORDER]
    cx, cy, cr = CLOSE
    out += [("close", (cx - cr - 3, cy - cr - 3, 2 * cr + 6, 2 * cr + 6)), ("grip", GRIP)]
    if S.tab == "eyes" and not eyes_running():
        out.append(("restart", RESTART))
    if S.tab == "settings" and sp.setup.step != "closed":
        out += [(name, rect) for name, rect, _, _ in spotify_buttons()]
    elif S.tab == "settings":
        rows = []
        for i, (key, _, _) in enumerate(ROWS):
            if key == "spotify":
                rows.append(("connect", connect_rect(i)))
            elif key in settings.CHOICES:
                rows += [(f"set:{key}:{option}", rect) for option, rect in choice_rects(i, key)]
            else:
                tx, ty, tw, th = toggle_rect(i)
                rows.append((f"toggle:{key}", (tx - 50, ty - 4, tw + 54, th + 8)))
        out += [(name, rect) for name, rect in rows if can_see(rect)]     # scrolled out of sight: not clickable
        out.append(("config", CONFIG_BUTTON))
    return out


def hit(p):
    for name, rect in buttons():
        if inside(p, rect):
            return name
    return None


def press(name):
    if name.startswith("tab:"):
        S.tab = name[4:]
    elif name == "close":
        quit_fives()
    elif name == "restart":
        start_eyes()
    elif name == "connect":
        sp.disconnect() if sp.connected() else sp.start()
    elif name.startswith("sp:"):
        sp.press(name[3:])
    elif name.startswith("set:"):
        _, key, option = name.split(":", 2)
        settings.put(key, option)
    elif name.startswith("toggle:"):
        key = name[7:]
        settings.put(key, not settings.get(key))
    elif name == "config":
        subprocess.run(["open", "-e", str(HERE / "config.py")])
    S.dirty = True


def key_pressed(ch):
    """A key typed while the FIVES window is in front. On the EYES tab they mean what they always meant."""
    if S.tab != "eyes" or not ch:
        return
    if ch == "q":
        quit_fives()
    elif ch in EYES_KEYS and eyes_running():
        eyes_link.Viewer.press(S.eyes, ch)


def where(v, event):
    """Where a mouse event landed, in design units (top-left origin)."""
    p = v.convertPoint_fromView_(event.locationInWindow(), None)
    k = v.bounds().size.width / W           # how much bigger than the design the window is right now
    return (p.x / k, p.y / k)


def apply_shape(width):
    """Cut the frosted glass to the round-cornered outline at this window width."""
    try:
        k = width / W

        def handler(rect):
            NSColor.whiteColor().set()
            path(frame_points(), k).fill()
            return True
        fx.setMaskImage_(NSImage.imageWithSize_flipped_drawingHandler_((width, H * k), True, handler))
        win.invalidateShadow()
    except Exception as e:
        print("hub: couldn't shape the glass:", e)


def resize_to(width, origin, size):
    """Resize keeping the top-left corner where it is (the Mac measures windows from the bottom-left)."""
    height = width * H / W
    win.setFrame_display_(NSMakeRect(origin.x, origin.y + size.height - height, width, height), True)
    apply_shape(width)
    S.dirty = True


# ---- the window -------------------------------------------------------------------------------------
class GlassWindow(NSWindow):
    def canBecomeKeyWindow(self):           # borderless windows can't take keys/clicks focus by default
        return True


class HubView(NSView):
    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):        # so key presses come to us
        return True

    def updateTrackingAreas(self):
        objc.super(HubView, self).updateTrackingAreas()
        for area in list(self.trackingAreas()):
            self.removeTrackingArea_(area)
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None))

    def mouseMoved_(self, event):
        name = hit(where(self, event))
        if name != S.hover:
            S.hover, S.dirty = name, True

    def scrollWheel_(self, event):
        """Trackpad, mouse wheel, or the hand-tracking scroll: moves the SETTINGS rows."""
        if S.tab != "settings" or sp.setup.step != "closed":
            return
        dy = event.scrollingDeltaY()
        scroll_settings(-dy if event.hasPreciseScrollingDeltas() else -dy * WHEEL_STEP)
        S.hover = hit(where(self, event))                   # the row under the pointer changed

    def mouseExited_(self, event):
        S.hover, S.dirty = None, True

    def mouseDown_(self, event):
        S.pressed = hit(where(self, event))
        S.mode = "resize" if S.pressed == "grip" else "move" if S.pressed is None else None
        S.start_mouse = NSEvent.mouseLocation()
        S.start_origin = self.window().frame().origin
        S.start_size = self.window().frame().size

    def mouseDragged_(self, event):
        now = NSEvent.mouseLocation()
        dx, dy = now.x - S.start_mouse.x, now.y - S.start_mouse.y
        if S.mode == "move":
            self.window().setFrameOrigin_((S.start_origin.x + dx, S.start_origin.y + dy))
        elif S.mode == "resize":
            try:
                # pull right or down = bigger (screen y counts upward, so down is a negative dy)
                grow = dx if abs(dx) > abs(dy * W / H) else -dy * W / H
                widest = NSScreen.mainScreen().visibleFrame().size.width
                resize_to(max(MIN_W, min(widest, S.start_size.width + grow)), S.start_origin, S.start_size)
            except Exception as e:
                print("hub resize error:", e)

    def mouseUp_(self, event):
        name, S.pressed, S.mode = S.pressed, None, None
        if name and name != "grip" and hit(where(self, event)) == name:
            try:
                press(name)
            except Exception as e:
                print("hub:", e)

    def keyDown_(self, event):
        try:
            key_pressed(str(event.charactersIgnoringModifiers() or "")[:1].lower())
        except Exception as e:
            print("hub key error:", e)

    def drawRect_(self, dirty):
        try:
            S.scale = self.bounds().size.width / W
            NSGraphicsContext.saveGraphicsState()
            t = NSAffineTransform.transform()
            t.scaleBy_(S.scale)
            t.concat()
            path(frame_points()).addClip()
            draw()
            NSGraphicsContext.restoreGraphicsState()
        except Exception as e:              # a drawing slip must never kill the window
            print("hub draw error:", e)


class Ticker(NSObject):
    def tick_(self, timer):
        """About 30 times a second: fetch the newest eyes picture, redraw what needs it."""
        if S.quitting:
            return
        seen = True
        if REST_WHEN_HIDDEN:
            try:
                seen = bool(win.occlusionState() & 2) and not win.isMiniaturized()     # 2 = some of it is on screen
            except Exception:
                pass
        # we want pictures while the EYES tab is showing (and until the first one arrives, to know eyes.py is up)
        watching = seen and eyes_running() and (S.tab == "eyes" or S.frame is None)
        link.watch(watching)
        redraw = S.dirty
        data = link.newest() if watching else None
        if data is not None:
            img = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(data, len(data)))
            if img is not None:
                size = struct.unpack_from("<ii", data, 18)          # a .bmp says its width and height here
                S.frame, S.frame_size = img, (max(1, abs(size[0])), max(1, abs(size[1])))
                redraw = True
        if S.tab == "eyes":
            if eyes_status() != "on":       # the waiting ring spins; "off" appears the moment eyes.py ends
                redraw = True
        elif S.tab == "brain":
            redraw = True                   # the orb breathes
        elif sp.setup.step != "closed" or int(time.time() * 30) % 15 == 0:
            redraw = True                   # the walkthrough moves on by itself (clipboard, sign-in)
        if redraw and seen:
            S.dirty = False
            view.setNeedsDisplay_(True)


def main():
    global link, win, view, fx
    try:                                    # the HUD font FIVES uses
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(str(HERE / "fonts" / name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)             # a normal app: Dock icon, Cmd+Tab
    screen = NSScreen.mainScreen().visibleFrame()
    width = max(MIN_W, min(W, screen.size.width - 60, (screen.size.height - 40) * W / H))
    height = width * H / W
    x = screen.origin.x + (screen.size.width - width) / 2
    y = screen.origin.y + (screen.size.height - height) / 2
    win = GlassWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(x, y, width, height), 0,
                                                                          NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setAcceptsMouseMovedEvents_(True)
    win.setTitle_("FIVES")
    fx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
    fx.setMaterial_(13)                     # frosted "HUD window" glass
    fx.setBlendingMode_(0)
    fx.setState_(1)
    try:
        fx.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
    except Exception:
        pass
    win.setContentView_(fx)
    view = HubView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
    view.setAutoresizingMask_(18)           # follows the window's size
    fx.addSubview_(view)
    apply_shape(width)

    link = eyes_link.Viewer()
    start_eyes()
    threading.Thread(target=brain_loop, daemon=True).start()
    ticker = Ticker.alloc().init()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1 / 30, ticker, "tick:", None, True)
    win.makeKeyAndOrderFront_(None)
    win.makeFirstResponder_(view)
    win.invalidateShadow()
    app.activateIgnoringOtherApps_(True)

    # DISENGAGE in the launcher, Ctrl-C, or closing Terminal: stop eyes.py too (checked on the next tick)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, quit_fives)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
