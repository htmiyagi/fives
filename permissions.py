"""Ask macOS for the three permissions FIVES needs, before eyes.py starts.

    Camera            to see your hand
    Accessibility     to move the mouse and click
    Input Monitoring  so the keyboard shortcuts work from any app

macOS never lets an app turn these on by itself. What this CAN do: check each one, pop up Apple's own
"allow?" box for the ones that are missing, and open the exact Settings page so it's one switch to flip.
The permission goes to whatever app FIVES runs inside (Terminal, when you double-click FIVES).

Run:  python permissions.py          (the FIVES launcher runs it for you every time; it's instant once all are on)
Exit code 0 = all on, 1 = something still needs a switch (then: Cmd+Q Terminal and open FIVES again).
"""

import subprocess
import sys
import threading
import time

SETTINGS = {
    "Camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "Accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "Input Monitoring": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
}


def camera_status():
    """'on', 'off' (denied), or 'ask' (never asked)."""
    try:
        import AVFoundation as AV
        s = AV.AVCaptureDevice.authorizationStatusForMediaType_(AV.AVMediaTypeVideo)
        return {3: "on", 2: "off", 1: "off"}.get(int(s), "ask")
    except Exception:
        return "unknown"


def ask_camera():
    """Pops up Apple's camera box and waits (up to a minute) for the answer."""
    try:
        import AVFoundation as AV
        from Foundation import NSDate, NSRunLoop
        done = threading.Event()
        AV.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AV.AVMediaTypeVideo, lambda ok: done.set())
        end = time.time() + 60
        while not done.is_set() and time.time() < end:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
    except Exception:
        import cv2                                   # fallback: opening the camera also makes macOS ask
        cam = cv2.VideoCapture(0)
        cam.read()
        cam.release()


def accessibility_on(prompt=False):
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        return None


def input_monitoring_on(prompt=False):
    try:
        import Quartz
        if prompt:
            Quartz.CGRequestListenEventAccess()      # Apple's own "allow?" box
        return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        return None


def check(prompt):
    return {"Camera": {"on": True, "off": False, "ask": False}.get(camera_status()),
            "Accessibility": accessibility_on(prompt),
            "Input Monitoring": input_monitoring_on(prompt)}


def request_all():
    """For the launcher's button: pop up Apple's boxes, open Settings for anything still off.
    Returns the names still missing (they need a switch flipped, then Terminal restarted)."""
    if camera_status() == "ask":
        ask_camera()
    status = check(prompt=True)
    missing = [name for name, ok in status.items() if ok is False]
    for name in missing:
        subprocess.run(["open", SETTINGS[name]])
    return missing


def main():
    status = check(prompt=False)
    if all(v is not False for v in status.values()) and camera_status() != "ask":
        return 0
    print("\nFIVES needs three permissions. macOS will show its own boxes: click Allow / Open System Settings.\n")
    if camera_status() == "ask":
        print("  Camera: asking...")
        ask_camera()
    status = check(prompt=True)                       # pops up the Accessibility + Input Monitoring boxes
    time.sleep(1.0)
    missing = [name for name, ok in status.items() if ok is False]
    for name, ok in status.items():
        print(f"  {'✓' if ok else '✗' if ok is False else '?'} {name}")
    if not missing:
        print("\nAll set!")
        return 0
    print("\nOpening the Settings page for each one that's still off.")
    print("Find 'Terminal' in the list and turn it ON (click + to add it if it's not there:")
    print("  Applications > Utilities > Terminal).")
    for name in missing:
        subprocess.run(["open", SETTINGS[name]])
        input(f"  -> turn Terminal ON under {name}, then press Enter here ")
    print("\nDone! Now QUIT Terminal completely (Cmd+Q) and open FIVES again, so macOS applies the new permissions.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
