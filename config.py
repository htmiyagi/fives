"""
config.py - FIVES's personality and settings.

This is the file you edit to make FIVES yours. Nothing in here "runs";
it's just values the other files read. Change a value, save, restart FIVES.
"""

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
NAME = "FIVES"
USER_NAME = "Hoyu"

# The system message (Lesson 1). This paragraph IS the personality.
PERSONALITY = (
    f"You are {NAME}, a personal assistant living on {USER_NAME}'s Mac. "
    "You are calm, sharp, and brief, like a good co-pilot. "
    "When a request can be done with one of your tools, call the tool. "
    "If nothing fits, just answer. Keep replies to one or two sentences."
)

# ---------------------------------------------------------------------------
# Brain (Lesson 1)
# ---------------------------------------------------------------------------
# Qwen 3.6 35B-A3B: a "mixture of experts" model. It knows as much as a 35B
# model but only uses 3B of its numbers per word, so it answers fast.
# About 23 GB, which fits comfortably in your 48 GB. Download it first:
#   ollama pull qwen3.6:35b
#
# Other options to try (change this one line, restart FIVES, compare):
#   "qwen3.6:35b-mlx"  same model, packaged for Apple's chip. Might be faster
#   "qwen3.6:27b"      denser and a bit smarter, but slower to answer
#   "qwen3.5:9b"       small and quick, if you want a lightweight fallback
MODEL = "qwen3.6:35b"

# "Thinking" lets the model reason silently before answering. Better for hard
# problems, but it adds seconds of delay. A command assistant wants speed.
#   False = off (fast)   True = on (slower, smarter)   None = model's default
THINK = False

# How many tokens (Lesson 1) the model can see at once. Bigger remembers more
# of the conversation but uses more memory. 16384 is plenty for FIVES.
CONTEXT_TOKENS = 16384

# 0 = pick the most likely action every time. Best for reliable tool use.
TEMPERATURE = 0

# How long Ollama keeps the model loaded in memory after your last request.
# Loading takes a while, so a long time here means FIVES answers fast all day.
KEEP_ALIVE = "2h"

# Safety valve: the most tool calls FIVES may make for one request.
MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# Voice (Lesson 5) - uses the Mac's built-in `say` command
# ---------------------------------------------------------------------------
SPEAK_REPLIES = False       # True = FIVES reads replies out loud
VOICE = "Samantha"          # see all voices: say -v '?'
SPEECH_RATE = 190           # words per minute

# ---------------------------------------------------------------------------
# Eyes (Lesson 4)
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0            # 0 = built-in camera. Try 1 for an external one
MIRROR = True               # flip the image so it moves like a mirror

# Pinch = thumb tip close to index tip. Measured as a fraction of hand size,
# so it works whether your hand is near or far from the camera.
PINCH_START = 0.20          # closer than this -> pinch begins
PINCH_END = 0.25            # farther than this -> pinch ends
# Letting go FAST: the pinch also ends as soon as the gap grows this much beyond
# the tightest it got. This is what makes clicks feel immediate. Pinches ending
# by accident while you drag? raise it (0.14). Clicks still feel slow? lower it (0.07).
PINCH_RELEASE_MARGIN = 0.10
# ...but while you are DRAGGING, only a clearly open hand counts as letting go.
# Drags still dropping by accident? raise it (0.50). Drops feel slow? lower it (0.35).
PINCH_DRAG_END = 0.40
PINCH_DEBUG = True
PINCH_CONFIRM_FRAMES = 3
PINCH_MAX_SPEED = 2.0
# Depth check: the thumb and index tips must be at about the same distance from the camera to count as a pinch
# (stops "thumb hidden behind the finger" fake pinches). Uses MediaPipe's depth guess, which is a bit noisy.
# With PINCH_DEBUG on, each pinch prints its "depth gap": real pinches should be small. Set this a bit above them.
# Real pinches getting blocked? raise it. Fakes still getting through? lower it. 0 = off.
PINCH_MAX_DEPTH = 0.35

# Camera picture size and speed. A smaller picture is faster to analyze,
# which means a higher frame rate and a less laggy cursor.
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# Smoothing for the fingertip (the "One Euro filter", see gestures.py).
# MIN_CUTOFF: steadiness when your finger is still. Lower = steadier but floatier.
# BETA: how fast it stops smoothing when you move. Higher = less lag, more shake.
# Tuning tip: shaky while holding still? lower MIN_CUTOFF.
#             laggy when moving fast?     raise BETA.
MIN_CUTOFF = 1.5
BETA = 8.0

# When you pinch, the click lands where your fingertip was this many seconds
# BEFORE the pinch was detected, so the finger dip doesn't move your click.
# Too much dip still? raise it (0.3). Click lands behind your motion? lower it.
REWIND_SECONDS = 0.25

# Cursor control. Off by default. Press "c" in the camera window to toggle.
CONTROL_CURSOR = False
# Only the middle part of the camera image maps to your screen, so you can
# reach the screen edges without your finger leaving the camera's view.
CURSOR_MARGIN = 0.22

# ---------------------------------------------------------------------------
# Clicking, dragging, right click, scroll (cursor mode only)
# ---------------------------------------------------------------------------
# LEFT CLICK: pinch (thumb + index), then let go. The click happens on release,
# like a real mouse. Two quick clicks in a row = double-click, three = triple.
#
# DRAG: pinch, then MOVE your hand. The button goes down and the cursor follows
# you until you let go. Great for dragging Chrome tabs and windows.
#
# HOLD: pinch and keep still. After HOLD_TO_PRESS_SECONDS the button goes down
# anyway (for press-and-hold menus). The ring around your fingertip fills up so
# you can see it coming. Set it to 0 to turn this off.
HOLD_TO_PRESS_SECONDS = 0.4

# How far your HAND (knuckles, not fingertip) must move, as a fraction of the
# camera picture, before a pinch becomes a drag. Clicks turning into drags?
# raise it. Drag feels stiff to start? lower it.
DRAG_DISTANCE = 0.05

# Tracking sometimes flickers for a frame. During a drag, the pinch must stay
# open this long before we let go, so you don't drop things by accident.
RELEASE_GRACE_SECONDS = 0.15

# If your hand leaves the camera mid-drag, let go after this long.
LOST_HAND_RELEASE_SECONDS = 0.3

# Double-click: the second click must come within this many seconds, and
# (roughly) in the same place.
DOUBLE_CLICK_SECONDS = 0.6     # air pinches are slower than mouse clicks, so this is generous
DOUBLE_CLICK_DISTANCE = 0.03

# RIGHT CLICK: pinch with thumb + index, and ALSO bring your middle fingertip to
# the thumb and keep it there for RIGHT_CLICK_FRAMES frames (3 = about 0.1 s), so a
# middle finger drifting by during a normal pinch doesn't count.
# RIGHT_CLICK_GAP is the middle-finger-to-thumb gap, as a fraction of hand size.
# Left clicks turning into right clicks? lower the gap (0.15) or raise the frames.
# Right click hard to trigger? raise the gap (0.25) or lower the frames.
RIGHT_CLICK_GAP = 0.20
RIGHT_CLICK_FRAMES = 3

# LETTING GO OF A DRAG: the cursor stays where you dropped things for this long, then
# glides to your fingertip, so it doesn't jump when your fingers open. Still jumps? raise
# the first one (0.25). Feels sluggish after a drag? lower them (0.08 / 0.1). 0 = off.
DRAG_SETTLE_SECONDS = 0.15
DRAG_SETTLE_BLEND = 0.15

# DRAW MODE (for sketch pads and drawing). Two ways to put ink down:
#   "key"   TAP DRAW_TOGGLE_HOTKEY to turn draw mode on (tap again to turn it off). Then your
#           hand only POINTS, and you HOLD DRAW_PEN_KEY to put ink down, like a graphics tablet.
#           Letting go of the key lifts the pen instantly. Clicking still works: tap the pen key.
#           (Best for precision. Pinch, drag and scroll-by-pinch are off while draw mode is on.)
#   "pinch" HOLD DRAW_HOTKEY, then pinch = ink down, let go = ink up (settings further below).
DRAW_PEN = "key"
DRAW_TOGGLE_HOTKEY = ["ctrl", "esc"]     # tap these together (Cmd + Escape)
DRAW_PEN_KEY = "alt"                    # any of "space", "cmd", "shift", "ctrl", "alt". If the
                                        # drawing site reacts to Space, try "ctrl".
# While the pen is down, your hand moves the cursor this fraction as far. 1 = same as normal,
# 0.5 = half as far (steadier, but you move more). Lift the pen to reposition. Too shaky? lower it.
DRAW_GAIN = 0.5
# Extra smoothing for the pen. Lower MIN_CUTOFF = steadier lines but a little lag; higher BETA =
# less lag on fast strokes. (Normal cursor: 1.5 and 8.0.)
DRAW_MIN_CUTOFF = 2.5
DRAW_BETA = 12.0
# Pen up: the cursor drifts back under your fingertip over about this many seconds (0 = never;
# it then stays wherever the last stroke left it). Smooth, never a jump.
DRAW_RESYNC_SECONDS = 0.5
# Hide the pen key from other apps while draw mode is on, so the page never sees it
# (stops sketch.io making a selection box when Option is held). Needs Accessibility permission.
DRAW_SWALLOW_PEN_KEY = True

# "pinch" draw mode only: hold this, then pinch = ink down. Cmd + Option by default.
# (Same key names as SCROLL_HOTKEY below. Set to [] to turn it off.)
DRAW_HOTKEY = ["cmd", "alt"]
# Where the stroke starts: your fingertip as it was this many seconds BEFORE the pinch dip.
DRAW_REWIND_SECONDS = 0.12
# Drawing holds on through a wobbly pinch: the pen lifts only when your thumb and finger are
# clearly apart (this gap, as a fraction of hand size). Pen drops while you draw? raise it
# (0.40). Pen lifts too slowly at the end of a stroke? lower it (0.28).
DRAW_HOLD_END = 0.35
# The pen STOPS following your hand once the pinch opens this much past its tightest,
# which cuts off the tail (it only lifts later, at DRAW_HOLD_END). Tail still there? lower it
# (0.035). The line stalls or stutters mid-stroke? raise it (0.07).
DRAW_LIFT_GUARD = 0.05

# SCROLL MODE: while you HOLD the hotkey below, your index pinch becomes a "finger on the
# screen": pinch, move your hand up/down and the page follows, let go and a flick keeps
# gliding. The cursor freezes in place and clicking is paused; let go of the keys and
# everything is back to normal. It works from any app.
# Hotkey: any of "cmd", "shift", "ctrl", "alt" (alt = Option). Modifier keys alone, no
# letter, so no app reacts to them. Needs  pip install pynput  and macOS Input Monitoring
# permission (System Settings > Privacy & Security > Input Monitoring > Terminal).
# Set to [] to turn scroll mode off completely.
SCROLL_HOTKEY = ["cmd", "shift"]
SCROLL_GAIN = 2500            # pixels scrolled when your hand crosses the whole picture height
SCROLL_DIRECTION = 1          # 1 = natural (like a trackpad). If it feels backwards, use -1
SCROLL_ENTER_FRAMES = 2       # the pinch must hold this many frames before scrolling starts
# Acceleration: faster swipes scroll farther (up to 4x). 0 = same distance at any speed.
SCROLL_ACCEL = 1.0
# Momentum: let go of the pinch while your hand is moving and the page keeps gliding,
# slowing to a stop over roughly this many seconds. Flick, lift, flick again.
# 0 turns the glide off. Glides too long? lower it (0.25). Stops too soon? raise it (0.6).
SCROLL_MOMENTUM_SECONDS = 0.4

# --- Eyes window look (hud.py) -------------------------------------------------
# True = the visor HUD. False = the plain camera picture (and the settings below are ignored).
# In the window:  H = switch camera / hand-only view,  [ and ] = less / more blue tint.
HUD = True
HUD_VIEW = "cam"            # "cam" = you in the viewport, "hand" = only your hand's wiring
HUD_STRENGTH = 0.35         # blue tint: 0 = your natural colors, 1 = full blue hologram. Try 0.2 to 0.6
HUD_WIDTH = 1280            # the window is shown this big (in points; a Retina screen has 2 pixels each)
HUD_HEIGHT = 720
HUD_SCALE = 2               # draw at this many times the pixels so text is sharp. 1 = faster, blurrier
HUD_GLOW = True             # bright outlines on you in the blue tint. Turn off if the window feels slow
HUD_DENOISE = 0.2           # 0 to 0.6: blends with the previous picture to calm camera grain. Too ghosty? lower
# With the HUD the camera runs at this bigger size for a sharper picture. Hand tracking still sees a
# small 4:3 copy (TRACK_WIDTH wide, cut from the middle), the same shape as before, so the feel and
# the speed don't change. Cursor range feels different? Set HUD_CAMERA_WIDTH/HEIGHT to 640 / 480.
HUD_CAMERA_WIDTH = 1280
HUD_CAMERA_HEIGHT = 720
TRACK_WIDTH = 640

# --- Music window (panel.py) ---
PANEL = True                          # False = don't start it
PANEL_HOTKEY = ["ctrl", "shift"]      # tap these two together to show / hide the window
PANEL_START_VISIBLE = True            # False = starts hidden until you tap the hotkey

# --- Music window (panel.py) ---
PANEL = True                          # False = don't start it
PANEL_HOTKEY = ["ctrl", "shift"]      # tap these two together to show / hide the window
PANEL_START_VISIBLE = True            # False = starts hidden until you tap the hotkey

# --- Finger flick: swipe an OPEN hand sideways to hide / show the music window ---
FLICK = True
FLICK_HIDE = "right"            # swipe this way to hide the window; the other way brings it back
FLICK_DISTANCE = 1.6            # how far to swipe, in hand sizes. Too easy to trigger? raise it (2.0). Won't trigger? lower it (1.2)
FLICK_SECONDS = 0.35            # within this many seconds (a slow drift is not a flick)
FLICK_COOLDOWN = 1.0            # seconds before the next flick can happen
FLICK_PALM_FACTOR = 1.2         # how straight the fingers must be (1.1 = easy, 1.35 = strict)
FLICK_FREEZE_CURSOR = True      # the cursor stays put while your palm is open
FLICK_DISTANCE = 1.2
FLICK_SECONDS = 0.45
FLICK_PALM_FACTOR = 1.15
FLICK_DEBUG = True
FLICK_DISTANCE = 0.7

# --- Two-finger point: aim index + middle (✌️) at a FIVES window to lock on to it (it glows) ---
# While locked on, the palm swipe for the wheel is paused, so the two can't get mixed up.
POINT_LOCK = True
POINT_FACTOR = 1.1             # how straight index + middle must be (and ring + pinky curled). 1.05 = easy, 1.25 = strict
POINT_LOCK_HOLD = 0.3          # seconds your aim must stay off a window before the lock moves or lets go (stops flicker)
POINT_DEBUG = True             # print "locked on: music" / "lock released" in Terminal
POINT_FLICK_COOLDOWN = 0.3     # after a ✌️ swipe, wait this long before the next (short, so the undo swipe works)
POINT_FLICK_DISTANCE = 0.35    # how far a ✌️ swipe must go, in hand sizes (the palm swipe uses FLICK_DISTANCE). Lower = more sensitive
POINT_SWIPE_GRACE = 0.5        # a ✌️ swipe still counts for a window you left this many seconds ago (fast swipes leave it early)

# --- Gesture recorder (GESTURES.md "tools"): saves hand points only, never pictures, to recordings/ (gitignored) ---
# Tap a combo to start recording with that label, tap it again to stop and save. Works from any app.
# "flick": ONE real attempt per recording (tap, flick once, tap). "not": normal hand use that must NOT
# trigger it (typing, pointing, reaching, waving), any length. Score them with: python score_gestures.py
RECORD_KEYS = {"flick": ["ctrl", "alt", "f"], "not": ["ctrl", "alt", "n"], "spin": ["ctrl", "alt", "s"]}

# --- Finger flick: from a ✌️ point, snap index + middle sideways while the PALM stays still ---
# Speeds are in hand sizes per second (so near / far from the camera doesn't matter). Tune with:
#   python score_gestures.py finger-flick       (and watch the "finger flick reached" lines live)
FINGER_FLICK_SPEED = 3.0       # how fast the fingertips must move RELATIVE to the palm. Lower = more sensitive, more accidents
FINGER_FLICK_PALM_MAX = 2.0    # the palm must move slower than this. Lower = stricter (whole-hand swipes never count); raise if your palm moves when you flick
FINGER_FLICK_SECONDS = 0.15    # speed is measured over this window, and the flick must start this soon after the ✌️. Raise for slower flicks
FINGER_FLICK_ARM_FRAMES = 3    # hold ✌️ this many frames before a flick counts. Raise = fewer accidents, lower = quicker
FINGER_FLICK_SIDEWAYS = 1.0    # sideways must be at least this many times the up/down motion. Raise = only clean left/right flicks
FINGER_FLICK_GRACE = 0.08      # forgive lost or blurry frames up to this long mid-flick (about 2 frames at 30 fps)
FINGER_FLICK_COOLDOWN = 0.4    # seconds after a flick before the next can happen
FINGER_FLICK_DEBUG = True      # print each attempt's peak speed vs the threshold (and the palm speed) in Terminal
POINT_UNDO_SECONDS = 1.0       # after flicking a window away: hold ✌️ and finger-flick back within this long to bring it back
# --- ↺ Spin: ☝️ index fingertip draws a fast circle (counterclockwise = restart the song, once it's wired) ---
# Not wired to anything yet: for now it only prints what it sees. Score it: python score_gestures.py spin
SPIN = True                    # listen for spins at all (never while draw mode is on)
SPIN_TURN = 250                # degrees of circle needed (360 = a full loop). Lower = easier. Below ~250 a half circle counts
SPIN_SECONDS = 0.8             # ...within this many seconds. This is what makes it FAST. Raise for slower spins
SPIN_MIN_RADIUS = 0.2          # how big the circle must be, in hand sizes. Raise if jitter or aiming counts
SPIN_ROUNDNESS = 0.4           # circle's box: short side ÷ long side (1 = perfectly round). Raise if waves count
SPIN_COOLDOWN = 1.0            # seconds after a spin before the next can happen
SPIN_GRACE = 0.1               # forgive a lost or blurry frame mid-spin up to this long
SPIN_DEBUG = True              # print each attempt's turn vs the threshold, and why it didn't fire
SPIN_METHOD = "center"         # how turning is measured: "center" (round the path's middle) or "heading" (how far
                               # the motion direction turns; no middle needed). Compare: python score_gestures.py spin-compare
SPIN_MIN_STEP = 0.02           # "heading" only: moves shorter than this (hand sizes) are noise, no direction. Raise if jitter adds turn
# HOLD TO SNAP (like Apple Pencil) - in draw mode, draw a shape and HOLD STILL at the end.
# FIVES undoes your wobbly stroke in the app (Cmd+Z) and redraws it clean: straight line,
# circle, ellipse, triangle, rectangle or square. Other strokes get smoothed. The app needs a working undo.
SNAP = True
SNAP_HOLD_SECONDS = 0.4      # how long to hold still. Snaps by accident? raise it. Too slow? lower it.
SNAP_HOLD_RADIUS = 12        # pixels you may wobble while "holding still"
SNAP_MIN_LENGTH = 60         # strokes shorter than this (pixels) never snap, so dots stay dots
SNAP_STEP_PX = 6             # spacing of the redrawn points
SNAP_UNDO_WAIT = 0.08        # seconds to let the app finish letting go / undoing. Not undoing? raise it.
SNAP_REPLAY_DELAY = 0.002    # seconds between redrawn points. Redraw looks jagged? raise it.

# SNAP PEN KEY: Option is now a plain pen. This key draws AND snaps after a short hold.
SNAP_PEN_KEY = "ctrl"      # any of "ctrl", "shift", "cmd", "space" (not the same as DRAW_PEN_KEY)
SNAP_QUICK_SECONDS = 0.1   # how long to hold still before it snaps. Snaps mid-stroke by accident? raise it.
SNAP_QUICK_RADIUS = 8      # pixels you may wobble while "holding still"

# SNAP PEN KEY: Option is now a plain pen. This key draws AND snaps after a short hold.
SNAP_PEN_KEY = "ctrl"      # any of "ctrl", "shift", "cmd", "space" (not the same as DRAW_PEN_KEY)
SNAP_QUICK_SECONDS = 0.1   # how long to hold still before it snaps. Snaps mid-stroke by accident? raise it.
SNAP_QUICK_RADIUS = 8      # pixels you may wobble while "holding still"

# SKETCH WINDOW. Tap Cmd+Esc: a sketch window opens (and draw mode turns on). Draw on a blank page or
# mark up a PDF. Option = plain pen, Control = pen that snaps shapes. Tap Cmd+Esc again to put it away.
# Needs:  pip install pymupdf        (turn SKETCH off to go back to drawing in whatever app you are in)
SKETCH = True
SKETCH_FOLDER = "~/Documents/FIVES Notes"   # where marked-up copies are saved (your original PDF is never changed)
SKETCH_AUTOSAVE = True                      # save the marked-up copy whenever you put the window away
SKETCH_SMOOTH_PASSES = 2                    # how much a finished stroke is smoothed (0 = none, 5 = very calm)
SKETCH_LIVE_FOLLOW = 0.6                    # 1 = ink goes exactly where you point; lower = calmer while drawing


# ---- PRECISION POINTER ----------------------------------------------------------------------------
# Move slowly and the cursor moves only part as far, so tiny targets are easy to hit. Move quickly and
# it moves 1:1 and catches back up to your fingertip, so it never wanders off. (The "PRISM" idea from VR.)
PRECISE = True
PRECISE_SPEED = 0.35          # below this hand speed (picture widths per second) the cursor slows down
PRECISE_MIN_SCALE = 0.35      # slowest: the cursor moves this fraction of your hand. Lower = more precise
PRECISE_CATCHUP_SPEED = 0.9   # moving this fast, the cursor snaps back under your finger quickest

# ---- DRAW MODE LIKE PAPER + SKETCH WINDOW CLICK-AWAY ---------------------------------------------
DRAW_SAME_SCALE = True     # draw mode: one fixed scale with the pen up or down, and the cursor stays where you
                           # lifted the pen (no sliding back). Letters come out the same size. False = old way.
SKETCH_CLICK_AWAY = True   # click anywhere outside the sketch window to put it away (draw mode turns off too)

# ---- SMOOTH CURSOR (glide) ------------------------------------------------------------------
# The camera only sees your hand ~30 times a second, so the cursor used to hop. With GLIDE on, it
# slides to each new spot in small steps (GLIDE_HZ times a second). Smoother, but it trails your
# hand by up to one camera frame.
GLIDE = True
GLIDE_SECONDS = 0       # how long each slide takes. 0 = automatic (one camera frame).
GLIDE_HZ = 120          # steps per second (your screen's refresh rate is a good choice)

# ---- LEAD ---------------------------------------------------------------------------------------
# The cursor trails your finger a little (camera + tracking + smoothing all take time). Lead draws it
# slightly AHEAD, along the way you're moving, to cancel that out. Only while pointing, not dragging,
# scrolling or drawing. Press l in the camera window to flip it on/off and compare.
LEAD = True
LEAD_SECONDS = 0.04     # how far ahead (0.04 = 40 ms). Still feels laggy? 0.06. Overshoots when you stop? 0.025
LEAD_MOST = 0.04        # the furthest it may lead, as a fraction of the picture
# ---- GLITCH GUARD ------------------------------------------------------------------------------
# Sometimes the tracker briefly puts your fingertip somewhere it can't be (dark room, finger turned
# away). If it "teleports" more than GLITCH_JUMP of the picture in one frame, keep the last good hand
# for up to GLITCH_HOLD_FRAMES frames. If it's still there after that, it was real: follow it.
GLITCH_GUARD = True
GLITCH_JUMP = 0.2            # fraction of the picture (0.2 = 20%). Lower catches more, but may ignore real flicks
GLITCH_HOLD_FRAMES = 2

# ---- CNN LEAD + DEPTH CHECK (added Nov 4) ------------------------------------------------------
# The Crosshair CNN as a lead (github.com/yagiht/crosshair). Press l to cycle: OFF -> DAMPED -> CNN.
LEAD_CNN = True
LEAD_CNN_PATH = "lead_model/deploy_cnn_1.pt"
LEAD_CNN_SCALE = 1.0    # 1.0 = the model's own guess (~33 ms ahead). Feels laggy? 1.2. Overshoots? 0.8
LEAD_START = "cnn"   # which mode FIVES starts in: "off", "damped", or "cnn"
# Depth check: thumb and index tips must be at about the same depth to count as a pinch. 0 = off.
PINCH_MAX_DEPTH = 0.35
# CNN lead fade-out: no push while your hand is still, so it's as steady as no lead.
LEAD_CNN_STILL = 0.04   # below this hand speed: no push. Still jittery when still? raise it (0.06)
LEAD_CNN_FULL = 0.07     # above this: the full push. Feels laggy when starting a move? lower it (0.12)
LEAD_CNN_CALM = 1.0     # smooths the push itself (1 = no smoothing, lower = calmer but a touch laggier)
