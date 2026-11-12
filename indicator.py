"""
indicator.py - the little "PLAYING ⚔️ Conquest ⚔️" note that flicks into the top-right corner when music changes.

It runs as its OWN tiny program (like confirm_box.py), so showing it never slows the music down:

    music tool ──▶ indicator.show("PLAYING", "⚔️ Conquest ⚔️") ──starts──▶ this program ──▶ slides in, fades out
                   returns right away                                     (gone after SHOW_SECONDS)

It ignores the mouse completely (clicks land on whatever is underneath) and never takes focus from your typing.
Turned on / off in Settings: NOW-PLAYING POPUP.

Try it from Terminal:   python indicator.py PLAYING "⚔️ Conquest ⚔️"
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- look (blues only, same family as hub.py) --------------------------------------------------------
W, H = 330, 62
MARGIN = 18                      # gap from the screen's top-right corner
CUT = 12                         # corners sliced off (top-left and bottom-right), the FIVES shape
SHOW_SECONDS = 2.5               # how long it's on screen in total
SLIDE_SECONDS = 0.22             # how long sliding in takes
FADE_SECONDS = 0.45              # how long fading out takes
SLIDE_DISTANCE = 40              # how far it slides in from the right
MAX_NAME = 26                    # longer names get cut with "…"
DEEP = (0.010, 0.035, 0.11)
NAVY = (0.04, 0.17, 0.46)
BLUE = (0.16, 0.60, 1.0)
SKY = (0.42, 0.76, 1.0)
WHITE = (0.90, 0.96, 1.0)

_last = None                     # the indicator that's showing now, so a new one can replace it


# ---- the part the rest of FIVES uses -----------------------------------------------------------------
def show(label: str, name: str) -> None:
    """Pop the indicator (if it's turned on in Settings). Returns right away and never raises: a popup that
    fails should never break the music."""
    global _last
    try:
        import settings                                    # here, so `python indicator.py` alone needs nothing else
        if not settings.get("now_playing_popup"):
            return
        if _last is not None and _last.poll() is None:     # skip, skip, skip: the newest replaces the old one
            _last.terminate()
        _last = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), label, name],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def short(name: str) -> str:
    """'A Really Long Playlist Name That Goes On' -> 'A Really Long Playlist Na…'"""
    return name if len(name) <= MAX_NAME else name[:MAX_NAME - 1].rstrip() + "…"


def placement(elapsed: float) -> tuple[float, float]:
    """(how far right of its resting spot, how see-through) at this moment. Slides in, rests, fades out."""
    if elapsed < SLIDE_SECONDS:
        t = elapsed / SLIDE_SECONDS
        ease = 1 - (1 - t) ** 3                            # fast then gentle, so it "flicks" in
        return SLIDE_DISTANCE * (1 - ease), ease
    fade_start = SHOW_SECONDS - FADE_SECONDS
    if elapsed < fade_start:
        return 0.0, 1.0
    return 0.0, max(0.0, 1 - (elapsed - fade_start) / FADE_SECONDS)


# ---- the window (only loaded when this file runs as its own program) ---------------------------------
def main(label: str, name: str) -> None:
    import objc
    from AppKit import (NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont,
                        NSFontAttributeName, NSForegroundColorAttributeName, NSKernAttributeName, NSMakeRect,
                        NSScreen, NSString, NSURL, NSView, NSWindow)
    from Foundation import NSObject, NSTimer
    from PyObjCTools import AppHelper

    try:                                                  # the FIVES font
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for file in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(str(HERE / "fonts" / file)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass

    def color(c, a=1.0):
        return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)

    def write(s, x, y, size, c, bold, kern):
        font = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size) or \
            NSFont.systemFontOfSize_(size)
        NSString.stringWithString_(s).drawAtPoint_withAttributes_(
            (x, y), {NSFontAttributeName: font, NSKernAttributeName: kern, NSForegroundColorAttributeName: color(c)})

    class NoteView(NSView):
        def isFlipped(self):                              # (0, 0) is the top-left, like hub.py
            return True

        def drawRect_(self, dirty):
            glass = NSBezierPath.bezierPath()             # a pill with two corners cut off
            for i, point in enumerate(((CUT, 1), (W - 1, 1), (W - 1, H - CUT), (W - CUT, H - 1), (1, H - 1),
                                       (1, CUT))):
                glass.moveToPoint_(point) if i == 0 else glass.lineToPoint_(point)
            glass.closePath()
            color(DEEP, 0.92).setFill()
            glass.fill()
            color(SKY, 0.55).setStroke()
            glass.setLineWidth_(1.2)
            glass.stroke()
            ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(14, 13, 36, 36))
            color(NAVY, 0.9).setFill()
            ring.fill()
            color(BLUE).setStroke()
            ring.setLineWidth_(1.5)
            ring.stroke()
            color(WHITE).setFill()
            if label.upper().startswith("PAUSED"):         # ⏸ two bars
                for x in (25, 34):
                    NSBezierPath.fillRect_(NSMakeRect(x, 23, 5, 16))
            else:                                         # ▶ a small triangle
                play = NSBezierPath.bezierPath()
                play.moveToPoint_((28, 23))
                play.lineToPoint_((39, 31))
                play.lineToPoint_((28, 39))
                play.closePath()
                play.fill()
            write(label.upper(), 64, 11, 12, SKY, True, 3.0)
            write(short(name), 64, 27, 19, WHITE, True, 1.0)

    class Ticker(NSObject):
        @objc.python_method
        def setup(self, win, rest_x):
            self.win, self.rest_x, self.started = win, rest_x, time.time()
            return self

        def tick_(self, timer):
            elapsed = time.time() - self.started
            if elapsed >= SHOW_SECONDS:
                NSApplication.sharedApplication().terminate_(None)
                return
            offset, alpha = placement(elapsed)
            origin = self.win.frame().origin
            self.win.setFrameOrigin_((self.rest_x + offset, origin.y))
            self.win.setAlphaValue_(alpha)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                          # 1 = no Dock icon, and it never takes focus
    screen = NSScreen.mainScreen().visibleFrame()        # "visible" = below the menu bar
    rest_x = screen.origin.x + screen.size.width - W - MARGIN
    y = screen.origin.y + screen.size.height - H - MARGIN
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(rest_x + SLIDE_DISTANCE, y, W, H), 0, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setAlphaValue_(0.0)
    win.setIgnoresMouseEvents_(True)                     # click-through: it's as if it isn't there
    win.setLevel_(25)                                    # 25 = above normal windows, like the volume popup
    win.setCollectionBehavior_(1 | 16 | 256)             # every desktop Space, stays put, even over full screen
    win.setContentView_(NoteView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H)))
    ticker = Ticker.alloc().init().setup(win, rest_x)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1 / 60, ticker, "tick:", None, True)
    win.orderFrontRegardless()                           # show it WITHOUT making it the active window
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "PLAYING", sys.argv[2] if len(sys.argv) > 2 else "")
