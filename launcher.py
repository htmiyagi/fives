"""The FIVES home window: start / stop FIVES, permissions, settings, update. No typing needed.

Same look as the music panel (panel.py): frosted glass, cut armor corners, neon 501st blue, Rajdhani font.

    ▌501ST LEGION                               ● ONLINE      [CLOSE]
    ▌FIVES
     SYSTEM CHECK
       CAMERA               ▮▮▮▮▮▮  GRANTED
       ACCESSIBILITY        ▮▮▮▮▮▮  GRANTED
       INPUT MONITORING     ▯▯▯▯▯▯  LOCKED
     > Run 'permissions' first.
    [  ENGAGE  ]   [PERMISSIONS] [SETTINGS]
                   [UPDATE]      [FOLDER]

  ENGAGE / DISENGAGE  opens the FIVES window (hub.py): tabs for EYES (hand tracking), BRAIN and SETTINGS.
                      hub.py runs eyes.py in the background. Messages still print in Terminal.
  PERMISSIONS         pops up Apple's own "allow?" boxes and opens the right Settings page for anything still off
                      (macOS applies new permissions after you quit Terminal with Cmd+Q and reopen FIVES)
  SETTINGS            opens config.py in TextEdit        FOLDER   opens the FIVES folder in Finder
  UPDATE              downloads the newest FIVES (your config.py is kept)
Drag the glass to move the window. CLOSE stops FIVES too.

Opened by double-clicking FIVES on your Desktop (install.sh makes that icon).  Run by hand:  python launcher.py
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import objc
from AppKit import (NSAppearance, NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSEvent, NSFont,
                    NSFontAttributeName, NSForegroundColorAttributeName, NSGraphicsContext, NSImage,
                    NSKernAttributeName, NSMakeRect, NSScreen, NSShadow, NSString, NSTrackingArea, NSURL, NSView,
                    NSVisualEffectView, NSWindow)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

import permissions

HERE = Path(__file__).resolve().parent
UPDATE = "curl -fsSL https://raw.githubusercontent.com/htmiyagi/fives/main/install.sh | bash -s -- --no-launch"

# ---- look (same palette as panel.py) ---------------------------------------------------------------
W, H, CUT = 460, 318, 16
BLUE = (0.16, 0.60, 1.0)
PALE = (0.55, 0.83, 1.0)
WHITE = (0.86, 0.95, 1.0)
GREY = (0.45, 0.63, 0.82)
INK = (0.02, 0.05, 0.12)
ON = (0.40, 0.78, 1.0)          # "granted / online": a bright ice blue (blues only)
OFF = (0.30, 0.42, 0.62)        # "locked / standby": a dim steel blue
TINT_ALPHA, GLOW = 0.42, 1.0

# ---- where everything sits (top-left origin, design units) -----------------------------------------
BUTTONS = {
    "close": (W - 96, 16, 72, 22),
    "engage": (24, 214, 196, 52),
    "permissions": (232, 214, 104, 23),
    "settings": (344, 214, 92, 23),
    "update": (232, 243, 104, 23),
    "folder": (344, 243, 92, 23),
}
ROWS = [("camera", "CAMERA"), ("accessibility", "ACCESSIBILITY"), ("input", "INPUT MONITORING")]


class State:
    proc = None              # the running hub.py (the tabbed FIVES window; it runs eyes.py)
    hover = None             # button under the pointer
    pressed = None
    perms = {"camera": None, "accessibility": None, "input": None}
    checked = 0.0
    msg = ""                 # one line of news under the system check
    busy = False             # updating / asking for permissions


S = State()


def running():
    return S.proc is not None and S.proc.poll() is None


def check_permissions():
    S.perms = {"camera": {"on": True, "off": False, "ask": False}.get(permissions.camera_status()),
               "accessibility": permissions.accessibility_on(False),
               "input": permissions.input_monitoring_on(False)}
    S.checked = time.time()


def ready():
    """Enough to run: camera + accessibility. Input Monitoring only matters for the keyboard shortcuts."""
    return S.perms.get("camera") is not False and S.perms.get("accessibility") is not False


# ---- drawing helpers (like panel.py) ---------------------------------------------------------------
def font(size, bold=False):
    f = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size)
    return f or (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))


def color(c, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)


def glow_on(radius, c=BLUE, alpha=0.9):
    NSGraphicsContext.saveGraphicsState()
    sh = NSShadow.alloc().init()
    sh.setShadowOffset_((0, 0))
    sh.setShadowBlurRadius_(radius * GLOW)
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


def line(x0, y0, x1, y1, c, width=1.0, alpha=1.0, glow=0):
    if glow:
        glow_on(glow)
    p = NSBezierPath.bezierPath()
    p.moveToPoint_((x0, y0))
    p.lineToPoint_((x1, y1))
    p.setLineWidth_(width)
    color(c, alpha).set()
    p.stroke()
    if glow:
        glow_off()


def box(rect, fill=None, fill_alpha=1.0):
    color(fill, fill_alpha).set()
    NSBezierPath.fillRect_(NSMakeRect(*rect))


def path(points):
    p = NSBezierPath.bezierPath()
    for i, pt in enumerate(points):
        (p.moveToPoint_ if i == 0 else p.lineToPoint_)(pt)
    p.closePath()
    return p


def poly(points, fill=None, stroke=None, width=1.0, fill_alpha=1.0, stroke_alpha=1.0, glow=0, glow_color=BLUE):
    if glow:
        glow_on(glow, glow_color)
    p = path(points)
    if fill is not None:
        color(fill, fill_alpha).set()
        p.fill()
    if stroke is not None:
        color(stroke, stroke_alpha).set()
        p.setLineWidth_(width)
        p.stroke()
    if glow:
        glow_off()


def chamfer(rect, c=6):
    x, y, w, h = rect
    return [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]


def frame_points(i=0.0):
    c = CUT
    return [(c, i), (W - c, i), (W - i, c), (W - i, H - c), (W - c, H - i), (c, H - i), (i, H - c), (i, c)]


def button(name, label, size=12, accent=BLUE):
    x, y, w, h = BUTTONS[name]
    hov, down = S.hover == name, S.pressed == name
    poly(chamfer((x, y, w, h), 6), fill=accent if (hov or down) else INK, fill_alpha=0.45 if down else 0.30 if hov else 0.35,
         stroke=WHITE if hov else accent, width=1.2, stroke_alpha=1.0 if hov else 0.75,
         glow=6 if hov else 3, glow_color=accent)
    lw = text_width(label, size, True, 2.5)
    text(label, x + (w - lw) / 2, y + (h - size * 1.25) / 2, size, WHITE if hov else PALE, True, 2.5,
         glow=4 if hov else 0, glow_color=accent)


def draw():
    # glass, top wash, grid, scan lines, sweep
    box((0, 0, W, H), fill=INK, fill_alpha=TINT_ALPHA)
    for i in range(0, 110, 2):
        box((0, i, W, 2), fill=BLUE, fill_alpha=0.18 * (1 - i / 110))
    for gx in range(0, W + 1, 24):
        line(gx, 0, gx, H, BLUE, 0.5, 0.07)
    for gy in range(0, H + 1, 24):
        line(0, gy, W, gy, BLUE, 0.5, 0.07)
    for sy in range(0, H, 3):
        line(0, sy, W, sy, WHITE, 0.6, 0.03)
    centre = (time.time() * 55) % (H + 120) - 60
    for k in range(-22, 23, 2):
        if 0 <= centre + k <= H:
            box((0, centre + k, W, 2), fill=PALE, fill_alpha=0.09 * (1 - abs(k) / 23))

    # frame + armor edges + tick ruler
    poly(frame_points(1), stroke=BLUE, width=1.8, glow=9)
    poly(frame_points(6), stroke=BLUE, width=0.8, stroke_alpha=0.5)
    line(CUT, 1, 1, CUT, WHITE, 3, 0.95, glow=7)
    line(W - CUT, H - 1, W - 1, H - CUT, WHITE, 3, 0.95, glow=7)
    for x in range(60, 220, 8):
        line(x, 1, x, 4 if (x // 8) % 5 else 7, WHITE, 1, 0.55)

    # header: name + status
    box((20, 14, 4, 34), fill=BLUE)
    text("501ST LEGION", 31, 12, 10, GREY, False, 3.0)
    text("FIVES", 31, 22, 26, WHITE, True, 6.0, glow=8)
    on = running()
    status = "UPDATING" if S.busy else "ONLINE" if on else "STANDBY"
    scol = ON if on else PALE
    sw = text_width(status, 12, True, 3.0)
    sx = W - 112 - sw
    if on:                                             # a pulsing dot while FIVES is running
        pulse = 0.55 + 0.45 * abs(((time.time() * 1.2) % 2) - 1)
        glow_on(8, ON)
        color(ON, pulse).set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(sx - 16, 21, 8, 8)).fill()
        glow_off()
    else:
        color(PALE, 0.7).set()
        p = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(sx - 16, 21, 8, 8))
        p.setLineWidth_(1.2)
        p.stroke()
    text(status, sx, 17, 12, scol, True, 3.0, glow=5 if on else 0, glow_color=scol)
    button("close", "CLOSE", 11)

    # system check
    text("HAND TRACKING SYSTEM", 31, 54, 10, GREY, False, 3.0, 0.8)
    line(24, 80, W - 24, 80, BLUE, 0.8, 0.35)
    text("SYSTEM CHECK", 24, 86, 11, PALE, True, 3.0)
    for k, (key, name) in enumerate(ROWS):
        y = 108 + k * 24
        ok = S.perms.get(key)
        c = ON if ok else OFF
        text(name, 40, y, 14, WHITE, True, 2.0)
        for b in range(8):                             # segmented status bar, like the HUD telemetry
            box((228 + b * 13, y + 4, 10, 10), fill=c, fill_alpha=0.95 if ok else 0.25)
        if ok:
            glow_on(5, c)
            box((228 + 7 * 13, y + 4, 10, 10), fill=c, fill_alpha=0.95)
            glow_off()
        word = "GRANTED" if ok else "LOCKED" if ok is False else "UNKNOWN"
        text(word, 340, y + 1, 12, c, True, 2.5, glow=4 if ok else 0, glow_color=c)
    hint = S.msg or ("> PRESS C ON THE EYES TAB FOR HAND CONTROL. Q QUITS FIVES." if on else
                     "> READY. (KEYBOARD SHORTCUTS NEED INPUT MONITORING.)" if ready() and S.perms.get("input") is False
                     else "> READY. PRESS ENGAGE." if ready() else "> RUN PERMISSIONS FIRST.")
    text(hint, 24, 184, 11, PALE, False, 1.5, 0.9)

    # buttons
    button("engage", "DISENGAGE" if on else "ENGAGE", 18, ON if not on and ready() else BLUE)
    button("permissions", "PERMISSIONS", 11)
    button("settings", "SETTINGS", 11)
    button("update", "UPDATE", 11)
    button("folder", "FOLDER", 11)
    text("FIVES  //  CONTROL", 24, H - 30, 10, GREY, False, 3.0, 0.7)


# ---- what the buttons do ---------------------------------------------------------------------------
def press(name):
    if name == "engage":
        if running():
            S.proc.terminate()
            S.msg = ""
        elif not ready():
            S.msg = "> CAMERA AND ACCESSIBILITY NEEDED FIRST: PRESS PERMISSIONS."
        else:
            S.proc = subprocess.Popen([sys.executable, str(HERE / "hub.py")], cwd=HERE)
            S.msg = ""
    elif name == "permissions":
        missing = permissions.request_all()
        check_permissions()
        S.msg = ("> ALL PERMISSIONS GRANTED." if not missing else
                 "> TURN 'TERMINAL' ON IN SETTINGS, THEN CMD+Q TERMINAL AND REOPEN FIVES."
                 if len(missing) > 1 or missing != ["Input Monitoring"] else
                 "> INPUT MONITORING: TURN 'TERMINAL' ON, THEN CMD+Q TERMINAL. IT SHOWS AFTER A RESTART.")
    elif name == "settings":
        subprocess.run(["open", "-e", str(HERE / "config.py")])
    elif name == "folder":
        subprocess.run(["open", str(HERE)])
    elif name == "update":
        if running():
            S.proc.terminate()
        S.busy, S.msg = True, "> DOWNLOADING THE NEWEST FIVES..."

        def job():
            ok = subprocess.run(["bash", "-c", UPDATE], cwd=HERE).returncode == 0
            S.busy = False
            S.msg = "> UPDATED. CLOSE AND REOPEN FIVES." if ok else "> UPDATE FAILED: SEE TERMINAL."
        threading.Thread(target=job, daemon=True).start()
    elif name == "close":
        if running():
            S.proc.terminate()
        NSApplication.sharedApplication().terminate_(None)


def where(view, event):
    """Where a mouse event landed in the view (top-left origin)."""
    p = view.convertPoint_fromView_(event.locationInWindow(), None)
    return (p.x, p.y)


def hit(p):
    x, y = p
    for name, (bx, by, bw, bh) in BUTTONS.items():
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return name
    return None


# ---- the window ------------------------------------------------------------------------------------
class GlassWindow(NSWindow):
    def canBecomeKeyWindow(self):           # borderless windows can't take keys/clicks focus by default
        return True


class HomeView(NSView):
    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def updateTrackingAreas(self):
        objc.super(HomeView, self).updateTrackingAreas()
        for area in list(self.trackingAreas()):
            self.removeTrackingArea_(area)
        self.addTrackingArea_(NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None))

    def mouseMoved_(self, event):
        S.hover = hit(where(self, event))

    def mouseExited_(self, event):
        S.hover = None

    def mouseDown_(self, event):
        S.pressed = hit(where(self, event))
        self.start_mouse = NSEvent.mouseLocation()
        self.start_origin = self.window().frame().origin

    def mouseDragged_(self, event):
        if S.pressed is None:                  # empty glass: drag to move the window
            now = NSEvent.mouseLocation()
            self.window().setFrameOrigin_((self.start_origin.x + now.x - self.start_mouse.x,
                                           self.start_origin.y + now.y - self.start_mouse.y))

    def mouseUp_(self, event):
        name, S.pressed = S.pressed, None
        if name and hit(where(self, event)) == name:
            try:
                press(name)
            except Exception as e:
                S.msg = f"> ERROR: {e}"
                print("launcher:", e)

    def drawRect_(self, dirty):
        try:
            NSGraphicsContext.saveGraphicsState()
            path(frame_points(0)).addClip()
            draw()
            NSGraphicsContext.restoreGraphicsState()
        except Exception as e:
            print("launcher draw error:", e)


class Ticker(NSObject):
    def tick_(self, timer):
        if time.time() - S.checked > 1.0:
            check_permissions()
        view.setNeedsDisplay_(True)


def main():
    global view
    try:                                    # the HUD font FIVES uses
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(str(HERE / "fonts" / name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)             # a normal app: Dock icon, Cmd+Tab, Cmd+Q
    screen = NSScreen.mainScreen().visibleFrame()
    x = screen.origin.x + (screen.size.width - W) / 2
    y = screen.origin.y + (screen.size.height - H) / 2
    win = GlassWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(x, y, W, H), 0,
                                                                          NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setAcceptsMouseMovedEvents_(True)
    win.setTitle_("FIVES")
    fx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
    fx.setMaterial_(13)                     # frosted "HUD window" glass
    fx.setBlendingMode_(0)
    fx.setState_(1)
    try:
        fx.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
    except Exception:
        pass

    def shape(rect):                        # cut the glass to the armor outline
        NSColor.whiteColor().set()
        path(frame_points(0)).fill()
        return True
    try:
        fx.setMaskImage_(NSImage.imageWithSize_flipped_drawingHandler_((W, H), True, shape))
    except Exception as e:
        print("launcher: couldn't shape the glass:", e)
    win.setContentView_(fx)
    view = HomeView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
    fx.addSubview_(view)
    check_permissions()
    ticker = Ticker.alloc().init()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.05, ticker, "tick:", None, True)
    win.makeKeyAndOrderFront_(None)
    win.invalidateShadow()
    app.activateIgnoringOtherApps_(True)

    def stop_fives():
        if running():
            S.proc.terminate()
    import atexit
    atexit.register(stop_fives)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
