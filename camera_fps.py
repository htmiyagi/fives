"""
camera_fps.py - how many frames per second can this Mac's camera really give?

A flick is over in a few frames, so 30 vs 60 fps matters. Cameras often only do 60 at some picture
sizes, and the driver sometimes says "60" but still delivers 30, so this MEASURES instead of asking.

Close FIVES first (only one program can read the camera reliably). Then:
    .venv/bin/python camera_fps.py
It tries a few sizes at 30 and 60 fps (about 4 seconds each) and prints what really arrived.
To use 60: set CAMERA_FPS = 60 (and a size that reached it) in config.py.
"""

import time

import cv2

import config

SIZES = [(1280, 720), (640, 480)]
RATES = [30, 60]
WARMUP_SECONDS = 1.0       # the first second is often slow while the camera adjusts its exposure
MEASURE_SECONDS = 3.0


def measure(width: int, height: int, fps: int) -> str:
    """Open the camera at this size and rate, count real frames, and describe the result in one line."""
    camera = cv2.VideoCapture(config.CAMERA_INDEX)
    try:
        if not camera.isOpened():
            return "couldn't open the camera (is FIVES still running?)"
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        camera.set(cv2.CAP_PROP_FPS, fps)
        got_w, got_h = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)), int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        claimed = camera.get(cv2.CAP_PROP_FPS)
        end_warmup = time.monotonic() + WARMUP_SECONDS
        while time.monotonic() < end_warmup:
            camera.read()
        frames, start = 0, time.monotonic()
        while time.monotonic() - start < MEASURE_SECONDS:
            ok, _ = camera.read()
            frames += ok
        real = frames / (time.monotonic() - start)
        return f"asked {fps:2d} fps at {width}x{height}: got {got_w}x{got_h}, it claims {claimed:.0f}, really {real:.1f} fps"
    finally:
        camera.release()


def main() -> None:
    print("Measuring the camera (close FIVES first). About 15 seconds...")
    for width, height in SIZES:
        for fps in RATES:
            print(" ", measure(width, height, fps))
    print("Pick the fastest line that's close to 60, and put its size + CAMERA_FPS = 60 in config.py.")


if __name__ == "__main__":
    main()
