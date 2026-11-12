"""
wheel.py - the wheel: FIVES's control room. A round menu with one wedge per FIVES window.

                    ╭──────────────╮
                  music   sketch
                settings    ●    brain        hover a wedge ▶ it grows and its name pops up
                     eyes                     click a wedge ▶ says "open <window>" and the wheel closes
                    ╰──────────────╯          click outside, or Esc ▶ the wheel closes

It runs as its own little program, like panel.py and sketch.py, and talks through plain text lines:
    stdin  (told)  : show / hide / toggle / quit
    stdout (tells) : "open music"  when a wedge is clicked
                     "shown" / "hidden"  when it appears or goes away
Whoever started it turns "open music" into actions.run("open_window", window="music").

Run by hand:   .venv/bin/python wheel.py          (shows right away; type show / hide / quit, or Ctrl-C)
               .venv/bin/python wheel.py --hidden (starts hidden)

The wedges and their order come from settings ("wheel_order"); the rules and math are in wheel_logic.py.
Look: the same as the music window (panel.py): frosted glass, grid, scan lines, neon frame with white armor
edges, armor-plate highlights. Blues only, Rajdhani. Sizes and colours are the constants just below: tweak freely.
"""

import math
import os
import signal
import sys
import threading
import time

import objc
from AppKit import (NSAppearance, NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont,
                    NSFontAttributeName, NSForegroundColorAttributeName, NSGraphicsContext, NSImage,
                    NSKernAttributeName, NSMakeRect, NSScreen, NSShadow, NSString, NSTrackingArea, NSURL, NSView,
                    NSVisualEffectView, NSWindow)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

import settings
import wheel_logic

# ---- look (layout calls: change freely) --------------------------------------------------------------
OUTER = 190                      # the ring's outer edge (points from the centre)
INNER = 64                       # the hole in the middle
GAP = 2.0                        # degrees of empty space between two wedges
DIM = 0.22                       # how much the rest of the screen darkens while the wheel is open (0 = not at all)
ICON_AT = 0.56                   # where the icon sits, from the hole (0) to the outer edge (1)
LABEL_SIZE = 22                  # the name that pops up on hover
DISC = OUTER + 10                # the frosted glass disc's edge
TINT_ALPHA = 0.36                # how dark the glass is (same as the music window). Lower = see more behind it
TEXT_ALPHA = 0.80                # how solid the writing is (same as the music window)
SWEEP = True                     # a faint bright band sliding down the glass, like the music window's hologram scan
BLACK = (0.006, 0.016, 0.05)     # near-black (the screen dimming)
INK = (0.02, 0.05, 0.12)         # the glass tint (same as the music window)
BLUE = (0.16, 0.60, 1.0)         # the FIVES neon blue (same as hub.py and the music window)
PALE = (0.55, 0.83, 1.0)
WHITE = (0.86, 0.95, 1.0)        # cool white
GREY = (0.45, 0.63, 0.82)        # cool blue-grey for quiet labels

TICK = 1 / 60                    # redraw 60 times a second while open (for the smooth grow)
EASE = 0.35                      # how quickly a wedge reaches its new size each tick (0..1, higher = snappier)
OPEN_SECONDS = 0.14              # the wheel pops open over this long
ESC = 53                         # the Esc key's macOS key code
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


# ---- small drawing helpers ---------------------------------------------------------------------------
def color(c, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)


def font(size, bold=False):
    f = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size)
    return f or (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))


def polygon(points, closed=True):
    p = NSBezierPath.bezierPath()
    for i, pt in enumerate(points):
        (p.moveToPoint_ if i == 0 else p.lineToPoint_)(pt)
    if closed:
        p.closePath()
    return p


def glow_on(radius):
    """Everything drawn until glow_off() gets a soft neon halo."""
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_((0, 0))
    shadow.setShadowBlurRadius_(radius)
    shadow.setShadowColor_(color(BLUE, 0.9))
    shadow.set()


def glow_off():
    NSGraphicsContext.restoreGraphicsState()


def paint(p, fill=None, fill_alpha=1.0, stroke=None, width=1.0, stroke_alpha=1.0, glow=0):
    """Fill and/or outline a shape, with an optional soft blue glow."""
    if glow:
        glow_on(glow)
    if fill is not None:
        color(fill, fill_alpha).set()
        p.fill()
    if stroke is not None:
        color(stroke, stroke_alpha).set()
        p.setLineWidth_(width)
        p.setLineCapStyle_(1)               # round ends
        p.stroke()
    if glow:
        glow_off()


def circle(cx, cy, r, **look):
    paint(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r)), **look)


def line(points, c, width=2.0, alpha=1.0, glow=0):
    paint(polygon(points, closed=False), stroke=c, width=width, stroke_alpha=alpha, glow=glow)


def text_style(size, c, alpha=1.0, bold=True, kern=2.0):
    return {NSFontAttributeName: font(size, bold), NSKernAttributeName: kern,
            NSForegroundColorAttributeName: color(c, alpha * TEXT_ALPHA)}


def text_mid(s, cx, cy, size, c, alpha=1.0, glow=0, bold=True, kern=2.0):
    """Text centred on (cx, cy)."""
    style = text_style(size, c, alpha, bold, kern)
    string = NSString.stringWithString_(s)
    w, h = string.sizeWithAttributes_(style)
    if glow:
        glow_on(glow)
    string.drawAtPoint_withAttributes_((cx - w / 2, cy - h / 2), style)
    if glow:
        glow_off()


def text_width(s, size, bold=True, kern=2.0):
    return NSString.stringWithString_(s).sizeWithAttributes_(text_style(size, WHITE, 1.0, bold, kern)).width


def rect(x, y, w, h, c, alpha):
    color(c, alpha).set()
    NSBezierPath.fillRect_(NSMakeRect(x, y, w, h))


def chamfer(x, y, w, h, cut=6):
    """A rectangle with its top-left and bottom-right corners cut off (the music window's armor-plate look)."""
    return [(x + cut, y), (x + w, y), (x + w, y + h - cut), (x + w - cut, y + h), (x, y + h), (x, y + cut)]


def arc(a0, a1, radius, cx, cy, steps=12):
    """Points along a circle from clock angle a0 to a1."""
    return [wheel_logic.point_at(a0 + (a1 - a0) * i / steps, radius, cx, cy) for i in range(steps + 1)]


def wedge_edges(index, count):
    """The clock angles where a wedge starts and ends (minus the little gap)."""
    half = wheel_logic.wedge_size(count) / 2 - GAP / 2
    mid = wheel_logic.wedge_middle(index, count)
    return mid - half, mid + half


def wedge_points(index, count, inner, outer, cx, cy, steps=24):
    """The outline of one wedge: along the outer edge, then back along the inner edge."""
    a0, a1 = wedge_edges(index, count)
    return arc(a0, a1, outer, cx, cy, steps) + arc(a1, a0, inner, cx, cy, steps)


# ---- placeholder icons (Hoyu will make Clone Wars style ones later) ----------------------------------
def icon(name, cx, cy, c, k=1.0):
    """A small picture for each window, about 30 points across (k makes it bigger)."""
    s = 1.3 * k
    if name == "music":                                    # a note
        circle(cx - 4 * s, cy + 8 * s, 5 * s, fill=c)
        line([(cx + 1 * s, cy + 8 * s), (cx + 1 * s, cy - 11 * s), (cx + 10 * s, cy - 7 * s)], c, 2.4 * k)
    elif name == "sketch":                                 # a pencil
        line([(cx - 9 * s, cy + 9 * s), (cx + 7 * s, cy - 7 * s)], c, 4.6 * k)
        line([(cx - 9 * s, cy + 9 * s), (cx - 11 * s, cy + 11 * s)], c, 2.0 * k)
    elif name == "brain":                                  # an orb with a ring (Rex)
        circle(cx, cy, 6 * s, fill=c)
        circle(cx, cy, 11 * s, stroke=c, width=1.6 * k, stroke_alpha=0.7)
    elif name == "eyes":                                   # a lens
        circle(cx, cy, 10 * s, stroke=c, width=2.2 * k)
        circle(cx, cy, 4 * s, fill=c)
    elif name == "settings":                               # two sliders
        for dy, knob in ((-5, 4), (5, -4)):
            line([(cx - 10 * s, cy + dy * s), (cx + 10 * s, cy + dy * s)], c, 2.2 * k)
            circle(cx + knob * s, cy + dy * s, 3.8 * s, fill=c)
    else:                                                  # a window we have no picture for yet
        circle(cx, cy, 8 * s, stroke=c, width=2.0 * k)


# ---- the view ----------------------------------------------------------------------------------------
class WheelView(NSView):
    """Draws the wheel and handles the mouse. Everything is in points, y down (isFlipped)."""

    def initWithFrame_(self, frame):
        self = objc.super(WheelView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.order = wheel_logic.clean_order(settings.get("wheel_order"))
        self.hovered = None                      # which wedge the mouse is over (None = none)
        self.grown = [1.0] * len(self.order)     # each wedge's size right now (eases toward its target)
        self.opening = 1.0                       # 0 = just appeared, 1 = fully open (the pop-open animation)
        self.on_pick = None                      # called with a window name when a wedge is clicked
        self.on_close = None                     # called when you click outside or press Esc
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    @objc.python_method
    def centre(self):
        b = self.bounds()
        return b.size.width / 2, b.size.height / 2

    @objc.python_method
    def reload_order(self):
        """Read the order again (it may have changed in Settings since last time)."""
        self.order = wheel_logic.clean_order(settings.get("wheel_order"))
        self.grown = [1.0] * len(self.order)
        self.hovered = None

    @objc.python_method
    def wedge_under(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        cx, cy = self.centre()
        pop = 0.85 + 0.15 * self.opening
        biggest = OUTER * (1 + wheel_logic.HOVER_GROW) * pop
        found = wheel_logic.wedge_at(p.x, p.y, cx, cy, INNER * pop, biggest, len(self.order))
        if found is None:
            return None
        reach = OUTER * self.grown[found] * pop        # only as far out as that wedge is drawn right now
        return found if math.hypot(p.x - cx, p.y - cy) <= reach else None

    @objc.python_method
    def step(self):
        """One animation tick: ease every wedge toward its target size. True if anything still moves."""
        moving = False
        count = len(self.order)
        for i in range(count):
            target = wheel_logic.growth(i, self.hovered, count)
            self.grown[i] += (target - self.grown[i]) * EASE
            if abs(target - self.grown[i]) > 0.001:
                moving = True
            else:
                self.grown[i] = target
        return moving

    # -- mouse and keys -------------------------------------------------------------------------------
    def updateTrackingAreas(self):
        for area in self.trackingAreas():
            self.removeTrackingArea_(area)
        options = 0x01 | 0x02 | 0x80 | 0x200       # entered/exited + moved + active always + follows the view's size
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), options, self, None))

    def mouseMoved_(self, event):
        under = self.wedge_under(event)
        if under != self.hovered:
            self.hovered = under
            self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        under = self.wedge_under(event)
        if under is None:
            if self.on_close:
                self.on_close()                  # clicked outside the ring (or in the hole): just close
        elif self.on_pick:
            self.on_pick(self.order[under])

    def keyDown_(self, event):
        if event.keyCode() == ESC and self.on_close:
            self.on_close()

    # -- drawing ----------------------------------------------------------------------------------------
    def drawRect_(self, dirty):
        try:
            self.draw_all()
        except Exception as err:        # a Python error inside AppKit's drawing would crash silently: say it instead
            print("wheel: drawing failed:", repr(err), file=sys.stderr)

    @objc.python_method
    def draw_all(self):
        color(BLACK, DIM * self.opening).set()
        NSBezierPath.fillRect_(self.bounds())                       # darken the rest of the screen a little
        cx, cy = self.centre()
        pop = 0.85 + 0.15 * self.opening                             # grows from 85% to full size as it opens
        count = len(self.order)
        self.draw_glass(cx, cy, DISC * pop)
        self.draw_frame(cx, cy, DISC * pop)
        for i, name in enumerate(self.order):
            if i != self.hovered:
                self.draw_wedge(i, name, cx, cy, pop, count)
        if self.hovered is not None:                                 # the hovered one last, so its glow is on top
            self.draw_wedge(self.hovered, self.order[self.hovered], cx, cy, pop, count)
        self.draw_header(cx, cy, pop)
        if self.hovered is not None:
            self.draw_label(self.order[self.hovered], self.hovered, cx, cy, pop, count)

    @objc.python_method
    def disc_rect(self):
        """The square around the glass disc (all that needs redrawing for the scan sweep)."""
        cx, cy = self.centre()
        return NSMakeRect(cx - DISC - 20, cy - DISC - 20, 2 * DISC + 40, 2 * DISC + 40)

    @objc.python_method
    def draw_glass(self, cx, cy, r):
        """The music window's glass, inside a circle: dark tint, a neon wash at the top, grid, scan lines."""
        a = self.opening
        NSGraphicsContext.saveGraphicsState()
        disc = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))
        disc.addClip()                                               # nothing below spills outside the circle
        color(INK, TINT_ALPHA * a).set()
        disc.fill()
        left, top = cx - r, cy - r
        for i in range(0, 120, 2):                                   # neon wash, fading out downward
            rect(left, top + i, 2 * r, 2, BLUE, 0.20 * (1 - i / 120) * a)
        for k in range(0, int(2 * r) + 1, 24):                       # faint grid
            line([(left + k, top), (left + k, top + 2 * r)], BLUE, 0.5, 0.08 * a)
            line([(left, top + k), (left + 2 * r, top + k)], BLUE, 0.5, 0.08 * a)
        for k in range(0, int(2 * r), 3):                            # scan lines
            rect(left, top + k, 2 * r, 0.6, WHITE, 0.035 * a)
        if SWEEP:                                                    # a bright band slides down every few seconds
            band = (time.time() * 55) % (2 * r + 120) - 60
            for k in range(-22, 23, 2):
                rect(left, top + band + k, 2 * r, 2, PALE, 0.10 * (1 - abs(k) / 23) * a)
        NSGraphicsContext.restoreGraphicsState()

    @objc.python_method
    def draw_frame(self, cx, cy, r):
        """Neon outer ring, thin inner ring, white armor edges at top-left and bottom-right, a tick ruler on top."""
        a = self.opening
        circle(cx, cy, r - 1, stroke=BLUE, width=1.8, stroke_alpha=a, glow=9)
        circle(cx, cy, r - 6, stroke=BLUE, width=0.8, stroke_alpha=0.5 * a)
        for mid in (315, 135):                                       # same corners as the music window's cuts
            line(arc(mid - 12, mid + 12, r - 1, cx, cy), WHITE, 3, 0.95 * a, glow=7)
        for n, angle in enumerate(range(-36, 37, 3)):                # tick ruler, every 5th tick longer
            length = 6 if n % 5 == 0 else 3
            line([wheel_logic.point_at(angle, r - 1, cx, cy), wheel_logic.point_at(angle, r - 1 - length, cx, cy)],
                 WHITE, 1, 0.55 * a)

    @objc.python_method
    def draw_wedge(self, i, name, cx, cy, pop, count):
        """Each wedge is styled like the music window's PREV / PLAY / NEXT buttons."""
        hot = i == self.hovered
        a = self.opening
        outer = OUTER * self.grown[i] * pop
        inner = INNER * pop
        shape = polygon(wedge_points(i, count, inner, outer, cx, cy))
        paint(shape, fill=BLUE, fill_alpha=(0.50 if hot else 0.07) * a, stroke=BLUE,
              width=1.5 if hot else 1.0, stroke_alpha=(1.0 if hot else 0.55) * a, glow=7 if hot else 2)
        if hot:
            self.draw_brackets(i, count, inner, outer, cx, cy)
        ix, iy = wheel_logic.point_at(wheel_logic.wedge_middle(i, count),
                                      inner + (outer - inner) * ICON_AT, cx, cy)
        icon(name, ix, iy, WHITE if hot else PALE, k=self.grown[i])

    @objc.python_method
    def draw_brackets(self, i, count, inner, outer, cx, cy):
        """White corner brackets on the hovered wedge, like the ones around the music window's album cover."""
        arm = 11                                                     # how long each bracket arm is (points)
        a0, a1 = wedge_edges(i, count)
        for radius, inward in ((outer, -1), (inner, 1)):
            turn = math.degrees(arm / radius)                        # the arm's length as an angle at this radius
            for edge, along in ((a0, 1), (a1, -1)):                  # an L: along the edge, then in toward the middle
                line(arc(edge + along * turn, edge, radius, cx, cy, 4)
                     + [wheel_logic.point_at(edge, radius + inward * arm, cx, cy)], WHITE, 2, 0.95, glow=5)

    @objc.python_method
    def draw_header(self, cx, cy, pop):
        """The middle of the wheel: a thin ring and the music window's header style."""
        a = self.opening
        circle(cx, cy, INNER * pop - 8, stroke=BLUE, width=0.8, stroke_alpha=0.5 * a)
        text_mid("501ST LEGION", cx, cy - 11, 8, GREY, a, bold=False, kern=2.5)
        text_mid("FIVES", cx, cy + 6, 17, WHITE, a, glow=7, kern=4.0)

    @objc.python_method
    def draw_label(self, name, i, cx, cy, pop, count):
        """The hovered window's name on an armor plate, popped up just outside its wedge."""
        lx, ly = wheel_logic.point_at(wheel_logic.wedge_middle(i, count),
                                      OUTER * (1 + wheel_logic.HOVER_GROW) * pop + 34, cx, cy)
        label = wheel_logic.WINDOWS.get(name, name.upper())
        w, h = text_width(label, LABEL_SIZE, kern=3.0) + 28, LABEL_SIZE + 10
        paint(polygon(chamfer(lx - w / 2, ly - h / 2, w, h, 7)), fill=BLUE, fill_alpha=0.40, stroke=WHITE,
              width=1.0, glow=5)
        text_mid(label, lx, ly, LABEL_SIZE, WHITE, glow=7, kern=3.0)


# ---- the window ------------------------------------------------------------------------------------------
class OverlayWindow(NSWindow):
    def canBecomeKeyWindow(self):              # a borderless window can't take key presses (Esc) unless we say so
        return True


class Controller(NSObject):
    def init(self):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self.visible = False
        return self

    @objc.python_method
    def build(self):
        screen = NSScreen.mainScreen().frame()           # the whole screen, so a click anywhere outside closes it
        self.win = OverlayWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            screen, 0, NSBackingStoreBuffered, False)    # 0 = borderless
        win = self.win
        win.setLevel_(25)                                # above normal windows
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(False)
        win.setAcceptsMouseMovedEvents_(True)
        win.setReleasedWhenClosed_(False)
        win.setCollectionBehavior_(1 | 16 | 256)         # all desktops + over full-screen apps
        size = screen.size
        whole = NSMakeRect(0, 0, size.width, size.height)
        holder = NSView.alloc().initWithFrame_(whole)
        win.setContentView_(holder)
        self.fx = NSVisualEffectView.alloc().initWithFrame_(whole)   # frosted glass, like the music window
        self.fx.setMaterial_(13)                                     # "HUD window" frosted glass
        self.fx.setBlendingMode_(0)                                  # blur what is BEHIND the window
        self.fx.setState_(1)                                         # stay frosted even when not active
        self.fx.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
        self.fx.setAutoresizingMask_(18)                             # follows the window's size
        holder.addSubview_(self.fx)
        self.view = WheelView.alloc().initWithFrame_(whole)          # drawn on top of the glass
        self.view.setAutoresizingMask_(18)
        self.view.on_pick = self.pick
        self.view.on_close = self.hide
        holder.addSubview_(self.view)

    @objc.python_method
    def shape_glass(self):
        """Only blur a circle in the middle (the window covers the whole screen, the glass doesn't)."""
        size = self.win.frame().size
        cx, cy = size.width / 2, size.height / 2

        def handler(rect):
            NSColor.whiteColor().set()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - DISC, cy - DISC, 2 * DISC, 2 * DISC)).fill()
            return True
        self.fx.setMaskImage_(NSImage.imageWithSize_flipped_drawingHandler_(size, True, handler))

    @objc.python_method
    def show(self):
        if self.visible:
            return
        self.view.reload_order()
        self.win.setFrame_display_(NSScreen.mainScreen().frame(), False)   # the screen you're on now
        self.shape_glass()
        self.visible = True
        self.view.opening = 0.0
        self.fx.setAlphaValue_(0.0)                                  # the glass fades in as the wheel pops open
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)  # so Esc comes to us
        self.win.makeKeyAndOrderFront_(None)
        self.win.makeFirstResponder_(self.view)
        say("shown")

    @objc.python_method
    def hide(self):
        if not self.visible:
            return
        self.visible = False
        self.win.orderOut_(None)
        NSApplication.sharedApplication().hide_(None)   # hand the keyboard back to the app you were using
        say("hidden")

    @objc.python_method
    def toggle(self):
        self.hide() if self.visible else self.show()

    @objc.python_method
    def pick(self, name):
        say(f"open {name}")
        self.hide()

    def tick_(self, timer):
        if not self.visible:
            return
        opening = self.view.opening < 1.0
        if opening:
            self.view.opening = min(1.0, self.view.opening + TICK / OPEN_SECONDS)
            self.fx.setAlphaValue_(self.view.opening)
        if self.view.step() or opening:
            self.view.setNeedsDisplay_(True)
        elif SWEEP:
            self.view.setNeedsDisplayInRect_(self.view.disc_rect())   # keep the scan band moving (just the disc)


def say(line: str) -> None:
    """Tell whoever started us something (one line on stdout)."""
    try:
        print(line, flush=True)
    except (BrokenPipeError, ValueError):       # nobody is listening any more
        pass


def load_fonts() -> None:
    """Load Rajdhani for this program only (the same font the rest of FIVES uses)."""
    try:
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(os.path.join(FONT_DIR, name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception as err:
        print("wheel: couldn't load the Rajdhani font, using the system font:", err, file=sys.stderr)


def main() -> None:
    load_fonts()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                          # "accessory": no Dock icon, no menu bar of its own
    controller = Controller.alloc().init()
    controller.build()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(TICK, controller, "tick:", None, True)

    def commands():
        """Whoever started us talks through stdin, one word per line. stdin closing means: quit."""
        for raw in sys.stdin:
            word = raw.strip().lower()
            if word in ("show", "hide", "toggle"):
                AppHelper.callAfter(getattr(controller, word))
            elif word == "quit":
                break
        AppHelper.callAfter(app.terminate_, None)

    threading.Thread(target=commands, daemon=True).start()
    if "--hidden" not in sys.argv:
        AppHelper.callAfter(controller.show)
    signal.signal(signal.SIGINT, lambda *a: app.terminate_(None))     # Ctrl-C quits (checked every tick)
    app.run()


if __name__ == "__main__":
    main()
