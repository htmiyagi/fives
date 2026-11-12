"""
confirm_box.py - the FIVES passcode box for risky actions ("Delete 'Gym' (32 songs)?").

It runs as its OWN little program (like eyes.py), so it works whether or not the FIVES window is open, and the
passcode you type stays inside it. It checks the passcode itself and only ever answers "yes" or "no":

    FIVES code ──▶ confirm_box.ask("Delete 'Gym'?") ──starts──▶ this program: you type here
                         ▲                                            │
                         └──────────── "yes" or "no" ─────────────────┘   (never the passcode)

    Rex (the model) only ever hears the tool's sentence afterwards, e.g. "Deleted Gym." / "Cancelled."

Keys:  type the passcode   Enter = confirm   Esc = cancel   Delete = remove a character
Drag the glass to move it. It cancels by itself after TIMEOUT_SECONDS.

Try it from Terminal:   python confirm_box.py "Delete 'Gym' (32 songs)?"      (prints yes or no)

The logic (tries, making a passcode) is in confirm_logic.py; the hashing is in passcode.py. This file only draws.
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

from AppKit import (NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont, NSFontAttributeName,
                    NSForegroundColorAttributeName, NSGraphicsContext, NSKernAttributeName, NSMakeRect,
                    NSParagraphStyleAttributeName, NSMutableParagraphStyle, NSScreen, NSShadow, NSString,
                    NSTextAlignmentCenter, NSURL, NSView, NSWindow)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from confirm_logic import Confirm, clock

HERE = Path(__file__).resolve().parent

# ---- look (blues only, same family as hub.py) --------------------------------------------------------
W, H = 520, 300
CUT = 18                         # how much is sliced off the top-left and bottom-right corners
GLASS_ALPHA = 0.94               # how solid the glass is (this box should be easy to read)
GRID = 0.06                      # faint grid. 0 = none
SEA = (0.030, 0.105, 0.30)       # glass top...
DEEP = (0.010, 0.035, 0.11)      # ...glass bottom
BLUE = (0.16, 0.60, 1.0)
SKY = (0.42, 0.76, 1.0)
PALE = (0.62, 0.86, 1.0)
WHITE = (0.90, 0.96, 1.0)
GREY = (0.50, 0.68, 0.88)
NAVY = (0.04, 0.17, 0.46)

# ---- where things sit (top-left origin) --------------------------------------------------------------
FIELD = (40, 150, 440, 46)       # the passcode dots
CANCEL = (40, 226, 205, 44)
CONFIRM = (275, 226, 205, 44)
TIMEOUT_SECONDS = 60             # cancel by itself if nobody answers
CLOSE_DELAY = 0.8                # how long "CONFIRMED" / "CANCELLED" shows before the box closes
ESC, RETURN, ENTER, DELETE = 53, 36, 76, 51     # Mac key codes


# ---- the part the rest of FIVES uses -----------------------------------------------------------------
def ask(question: str) -> bool:
    """Show the box and wait for the answer. True only if the right passcode was typed (or a new one was made).
    Anything going wrong counts as "no", so a broken box can never approve something."""
    try:
        reply = subprocess.run([sys.executable, str(Path(__file__).resolve()), question],
                               capture_output=True, text=True, timeout=TIMEOUT_SECONDS + 30)
        return reply.stdout.strip().splitlines()[-1:] == ["yes"]
    except Exception:
        return False


# ---- drawing helpers ---------------------------------------------------------------------------------
def font(size: float, bold: bool = False):
    f = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size)
    return f or (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))


def color(c: tuple, a: float = 1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)


def attrs(size: float, c: tuple, bold: bool = False, kern: float = 1.5, centred: bool = False) -> dict:
    a = {NSFontAttributeName: font(size, bold), NSKernAttributeName: kern, NSForegroundColorAttributeName: color(c)}
    if centred:
        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(NSTextAlignmentCenter)
        a[NSParagraphStyleAttributeName] = style
    return a


def text_in(s: str, rect: tuple, size: float, c: tuple, bold: bool = False, centred: bool = True) -> None:
    """Text inside a box, wrapped onto more lines if it's long."""
    NSString.stringWithString_(s).drawInRect_withAttributes_(NSMakeRect(*rect), attrs(size, c, bold, centred=centred))


def glowing(radius: float, c: tuple = BLUE, alpha: float = 0.8):
    """Turn on a soft glow for whatever is drawn next (until NSGraphicsContext.restoreGraphicsState())."""
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_((0, 0))
    shadow.setShadowBlurRadius_(radius)
    shadow.setShadowColor_(color(c, alpha))
    shadow.set()


def cut_shape(rect: tuple, cut: float):
    """A rectangle with its top-left and bottom-right corners sliced off (the FIVES plate shape)."""
    x, y, w, h = rect
    p = NSBezierPath.bezierPath()
    for i, point in enumerate([(x + cut, y), (x + w, y), (x + w, y + h - cut), (x + w - cut, y + h), (x, y + h),
                               (x, y + cut)]):
        (p.moveToPoint_ if i == 0 else p.lineToPoint_)(point)
    p.closePath()
    return p


def inside(point, rect: tuple) -> bool:
    x, y, w, h = rect
    return x <= point.x <= x + w and y <= point.y <= y + h


# ---- the window --------------------------------------------------------------------------------------
class Box:
    """Everything this running box knows (one box per program)."""
    logic = None                 # the Confirm from confirm_logic.py
    started = 0.0
    finished_at = None           # when the answer was decided (the box closes CLOSE_DELAY later)
    hover = None                 # "cancel" / "confirm" / None
    reported = False


B = Box()


class BoxWindow(NSWindow):
    def canBecomeKeyWindow(self):                    # borderless windows can't take key presses by default
        return True


class BoxView(NSView):
    def isFlipped(self):                             # top-left origin, like hub.py
        return True

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def keyDown_(self, event):
        code = event.keyCode()
        if code == ESC:
            B.logic.cancel()
        elif code in (RETURN, ENTER):
            B.logic.submit()
        elif code == DELETE:
            B.logic.backspace()
        else:
            for char in event.characters() or "":
                B.logic.type_char(char)
        self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        if inside(point, CANCEL):
            B.logic.cancel()
        elif inside(point, CONFIRM):
            B.logic.submit()
        else:
            self.window().performWindowDragWithEvent_(event)     # drag the glass to move the box
        self.setNeedsDisplay_(True)

    def mouseMoved_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        B.hover = "cancel" if inside(point, CANCEL) else "confirm" if inside(point, CONFIRM) else None

    def drawRect_(self, rect):
        draw_glass()
        draw_words()
        draw_field()
        draw_buttons()
        draw_timer()


def draw_glass() -> None:
    shape = cut_shape((1, 1, W - 2, H - 2), CUT)
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    for row in range(H):                             # the glass: SEA at the top fading to DEEP at the bottom
        t = row / H
        color(tuple(SEA[i] + (DEEP[i] - SEA[i]) * t for i in range(3)), GLASS_ALPHA).set()
        NSBezierPath.fillRect_(NSMakeRect(0, row, W, 1))
    color(BLUE, GRID).set()
    for x in range(0, W, 20):                        # the faint grid
        NSBezierPath.fillRect_(NSMakeRect(x, 0, 1, H))
    for y in range(0, H, 20):
        NSBezierPath.fillRect_(NSMakeRect(0, y, W, 1))
    NSGraphicsContext.restoreGraphicsState()
    glowing(10)
    color(BLUE, 0.9).set()
    shape.setLineWidth_(1.5)
    shape.stroke()
    NSGraphicsContext.restoreGraphicsState()


def draw_words() -> None:
    logic = B.logic
    NSString.stringWithString_("◆  FIVES  ·  CONFIRM").drawAtPoint_withAttributes_(
        (40, 22), attrs(13, SKY, bold=True, kern=3))
    text_in(logic.question, (40, 46, 440, 60), 24, WHITE, bold=True)
    warning = any(word in logic.message for word in ("WRONG", "SHORT", "MATCH", "LOCKED"))
    text_in(logic.message, (40, 112, 440, 22), 14, SKY if warning else PALE, bold=warning)


def draw_field() -> None:
    logic = B.logic
    field = cut_shape(FIELD, 8)
    color(DEEP, 0.9).set()
    field.fill()
    glowing(6, BLUE, 0.6)
    color(BLUE, 0.85).set()
    field.setLineWidth_(1.2)
    field.stroke()
    NSGraphicsContext.restoreGraphicsState()
    x, y, w, h = FIELD
    if logic.mode == "locked":                       # locked: the field shows the countdown instead of dots
        text_in(f"LOCKED   {clock(logic.store.locked_for())}", (x, y + 9, w, h - 9), 22, SKY, bold=True)
        return
    count = len(logic.typed)
    gap = 22
    start = x + w / 2 - (count - 1) * gap / 2
    glowing(8, SKY, 0.9)
    color(WHITE).set()
    for i in range(count):                           # one glowing dot per character, never the character
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(start + i * gap - 6, y + h / 2 - 6, 12, 12)).fill()
    NSGraphicsContext.restoreGraphicsState()
    if logic.result is None and int(time.time() * 2) % 2 == 0:     # a blinking caret
        caret_x = start + count * gap - (gap / 2 if count else 0)
        color(SKY, 0.9).set()
        NSBezierPath.fillRect_(NSMakeRect(caret_x, y + 11, 2, h - 22))
    if logic.mode == "enter" and logic.result is None:     # tries left before the next lock, as small circles
        for i in range(logic.store.TRIES_PER_LOCK):
            filled = i < logic.tries_left
            circle = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x + w - 54 + i * 16, y - 18, 9, 9))
            color(SKY if filled else GREY, 0.95 if filled else 0.35).set()
            circle.fill() if filled else circle.stroke()


def draw_buttons() -> None:
    for name, rect, label in (("cancel", CANCEL, "CANCEL"), ("confirm", CONFIRM, "CONFIRM")):
        shape = cut_shape(rect, 9)
        hot = B.hover == name
        if name == "confirm" and B.logic.mode == "locked":     # switched off while locked
            color(BLUE, 0.18).set()
            shape.fill()
            ink = GREY
        elif name == "confirm":                      # the main button is solid blue
            glowing(14 if hot else 8)
            color(SKY if hot else BLUE).set()
            shape.fill()
            NSGraphicsContext.restoreGraphicsState()
            ink = NAVY
        else:
            color(BLUE, 0.22 if hot else 0.10).set()
            shape.fill()
            color(BLUE, 0.9).set()
            shape.setLineWidth_(1.2)
            shape.stroke()
            ink = WHITE if hot else PALE
        x, y, w, h = rect
        text_in(label, (x, y + 10, w, h - 10), 18, ink, bold=True)


def draw_timer() -> None:
    """A thin bar along the bottom that shrinks as the box runs out of time."""
    left = max(0.0, 1 - (time.time() - B.started) / TIMEOUT_SECONDS)
    color(BLUE, 0.7).set()
    NSBezierPath.fillRect_(NSMakeRect(40, H - 14, (W - 80 - CUT) * left, 2))


# ---- keeping the keys private ------------------------------------------------------------------------
def secure_typing(on: bool) -> None:
    """macOS "secure input": while it's on, other apps can't listen to the keyboard (the same thing password
    boxes do). Best effort: if it isn't available, the box still works."""
    try:
        carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
        (carbon.EnableSecureEventInput if on else carbon.DisableSecureEventInput)()
    except Exception:
        pass


# ---- running ------------------------------------------------------------------------------------------
class Ticker(NSObject):
    def tick_(self, timer):
        B.logic.refresh()                            # the lock countdown (and unlocking when it runs out)
        if B.logic.result is None and time.time() - B.started > TIMEOUT_SECONDS:
            B.logic.cancel()
            B.logic.message = "TIMED OUT. CANCELLED"
        if B.logic.result is not None and B.finished_at is None:
            B.finished_at = time.time()
        if B.finished_at is not None and time.time() - B.finished_at > CLOSE_DELAY:
            finish()
        view.setNeedsDisplay_(True)


def finish() -> None:
    """Print the answer (just yes or no) and close."""
    if B.reported:
        return
    B.reported = True
    secure_typing(False)
    print("yes" if B.logic.result else "no", flush=True)
    NSApplication.sharedApplication().terminate_(None)


def register_fonts() -> None:
    try:
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(str(HERE / "fonts" / name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass


def main(question: str) -> None:
    global view
    register_fonts()
    B.logic, B.started = Confirm(question), time.time()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                      # 1 = no Dock icon: it's a popup, not an app
    screen = NSScreen.mainScreen().visibleFrame()
    frame = NSMakeRect(screen.origin.x + (screen.size.width - W) / 2,
                       screen.origin.y + (screen.size.height - H) / 2 + 80, W, H)
    win = BoxWindow.alloc().initWithContentRect_styleMask_backing_defer_(frame, 0, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setLevel_(3)                                 # 3 = floats above normal windows
    win.setAcceptsMouseMovedEvents_(True)
    view = BoxView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
    win.setContentView_(view)
    ticker = Ticker.alloc().init()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1 / 30, ticker, "tick:", None, True)
    win.makeKeyAndOrderFront_(None)
    win.makeFirstResponder_(view)
    app.activateIgnoringOtherApps_(True)
    secure_typing(True)
    try:
        AppHelper.runEventLoop()
    finally:
        secure_typing(False)
        if not B.reported:                           # closed some other way: that's a no
            print("no", flush=True)


view = None

if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "Are you sure?")
