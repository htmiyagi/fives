"""
hotkey.py - notice keys you press, even when another app is in front.

Why a separate file: eyes.py's camera window only hears keys while IT is the
front window. If you're clicking around in Chrome, Chrome gets your keystrokes.
A "global" listener hears every key press on the Mac, whatever app is in front.

Two things you can ask a HotkeyWatcher:
  .down          True while every key in the combo is held        (hold Cmd+Shift to scroll)
  .consume_tap() True ONCE when the combo was pressed and let go   (tap Cmd+Option to toggle)
                 with nothing else pressed in between

Normally it only LISTENS: a key does exactly what it always did in the app in front.
HotkeyWatcher.set_swallow([...]) can HIDE chosen keys from other apps for a while (we use it
so a drawing site never sees the pen key). Hidden keys need Accessibility permission too.

The first time, macOS asks for permission: System Settings > Privacy & Security >
Input Monitoring > turn on Terminal (or the app you run Python from), then restart.
"""

import time

# The number keys along the top, by their macOS key code. (A number key has no "name" in pynput,
# and with Option held it reports a symbol like ™ instead of "2", so the key code is the reliable way.)
DIGIT_KEYCODES = {18: "1", 19: "2", 20: "3", 21: "4", 23: "5", 22: "6", 26: "7", 28: "8", 25: "9"}
# Letter keys the same way (with Ctrl or Option held, the "character" would be something else).
LETTER_KEYCODES = {0: "a", 11: "b", 8: "c", 2: "d", 14: "e", 3: "f", 5: "g", 4: "h", 34: "i", 38: "j", 40: "k",
                   37: "l", 46: "m", 45: "n", 31: "o", 35: "p", 12: "q", 15: "r", 1: "s", 17: "t", 32: "u",
                   9: "v", 13: "w", 7: "x", 16: "y", 6: "z"}
CODE_KEYS = {**DIGIT_KEYCODES, **LETTER_KEYCODES}      # every key we know by its code

# Each name you can use in config, and the keys that count for it.
# (Left and right versions of a key both count.)
KEY_GROUPS = {
    "cmd": ("cmd", "cmd_l", "cmd_r"),
    "shift": ("shift", "shift_l", "shift_r"),
    "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
    "alt": ("alt", "alt_l", "alt_r", "alt_gr"),     # "alt" is the Option key on a Mac
    "option": ("alt", "alt_l", "alt_r", "alt_gr"),
    "space": ("space",),
    "esc": ("esc",),
    **{key: (key,) for key in CODE_KEYS.values()},                 # "1" ... "9", "a" ... "z"
}

# macOS key codes, so we can recognise a key before anyone else sees it (for swallowing).
KEYCODE_NAMES = {
    58: "alt_l", 61: "alt_r", 55: "cmd_l", 54: "cmd_r", 56: "shift_l", 60: "shift_r",
    59: "ctrl_l", 62: "ctrl_r", 49: "space", 53: "esc", **DIGIT_KEYCODES,
}
MODIFIER_KEYCODES = {58, 61, 55, 54, 56, 60, 59, 62}     # these arrive as "flags changed", not key down/up
OPTION_KEYCODES = {58, 61}                                # left and right Option
EVENT_KEY_DOWN, EVENT_KEY_UP, EVENT_FLAGS_CHANGED = 10, 11, 12

MAX_TAP_SECONDS = 1.0       # a "tap" must be over within this long (longer = you were holding it)


def key_name(key) -> str:
    """pynput's key -> our name for it ("alt_l", "esc", "3"...), or "" for keys we don't use."""
    return getattr(key, "name", None) or CODE_KEYS.get(getattr(key, "vk", None), "")


def should_hide(name: str, swallow, swallow_with_option, option_down: bool) -> bool:
    """Hide this key press from other apps? Always for `swallow`; for `swallow_with_option`, only
    while Option is held (so Option+2 opens a wedge instead of typing ™, but a plain 2 still types 2)."""
    return name in swallow or (option_down and name in swallow_with_option)


class HotkeyWatcher:
    """Watches for one key combo. Several watchers share ONE keyboard listener,
    because macOS can crash (zsh: abort) when a program runs two of them."""

    _listener = None      # the single shared pynput listener
    _held = set()         # key names that are down right now (shared by all watchers)
    _watchers = []        # every running watcher (told about each key press)
    _swallow = frozenset()      # key names to hide from other apps right now (see set_swallow)
    _swallow_with_option = frozenset()  # key names to hide only while Option is held (see set_swallow_with_option)
    _swallowed = set()          # keycodes whose press we hid (so we hide their release too)
    _mod_down = set()           # modifier keycodes we think are down (flags-changed events only say "changed")

    def __init__(self, names):
        unknown = [n for n in names if n not in KEY_GROUPS]
        if unknown:
            raise ValueError(f"Unknown key {unknown}. Use any of: {', '.join(KEY_GROUPS)}")
        self.names = list(names)
        self.keys = {k for n in names for k in KEY_GROUPS[n]}   # every key name that belongs to the combo
        self.ok = False
        self._taps = 0            # finished taps nobody has asked about yet
        self._in_progress = False
        self._tainted = False     # another key was pressed during the combo: not a clean tap
        self._was_full = False    # every key of the combo was down at the same time
        self._t_start = 0.0

    # -- asking ---------------------------------------------------------------
    @property
    def down(self) -> bool:
        """True while every key in the combo is held."""
        return self.ok and self._all_held()

    def consume_tap(self) -> bool:
        """True once per tap (the combo pressed together, then let go, nothing else pressed)."""
        if self._taps:
            self._taps = 0
            return True
        return False

    def _all_held(self) -> bool:
        held = HotkeyWatcher._held
        return all(any(k in held for k in KEY_GROUPS[n]) for n in self.names)

    # -- told by the listener -------------------------------------------------
    def _on_press(self, name: str) -> None:
        if name in self.keys:
            if not self._in_progress:
                self._in_progress, self._tainted, self._was_full = True, False, False
                self._t_start = time.monotonic()
            if self._all_held():
                self._was_full = True
        elif self._in_progress:
            self._tainted = True            # some other key: this is a different shortcut

    def _on_release(self, name: str) -> None:
        if name in self.keys and self._in_progress:
            clean = (self._was_full and not self._tainted
                     and time.monotonic() - self._t_start <= MAX_TAP_SECONDS)
            if clean:
                self._taps += 1
            self._in_progress = False

    # -- swallowing -------------------------------------------------------------
    @classmethod
    def set_swallow(cls, names) -> None:
        """Hide these keys (e.g. ["alt"]) from every other app until called again with [].
        Only keys pressed AFTER this are hidden, and a hidden press always has its release hidden
        too, so no app is ever left thinking a key is stuck. Does nothing if the listener isn't running."""
        cls._swallow = frozenset(k for n in names for k in KEY_GROUPS[n])

    @classmethod
    def set_swallow_with_option(cls, names) -> None:
        """Like set_swallow, but these keys are only hidden while Option is held down."""
        cls._swallow_with_option = frozenset(k for n in names for k in KEY_GROUPS[n])

    @classmethod
    def _intercept(cls, event_type, event):
        """Called by macOS-level hook BEFORE any app sees the key. Return the event to let it
        through, or None to hide it. Any trouble -> let it through (never block the keyboard)."""
        try:
            import Quartz
            code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            name = KEYCODE_NAMES.get(code)
            if name is None or event_type not in (EVENT_KEY_DOWN, EVENT_KEY_UP, EVENT_FLAGS_CHANGED):
                return event
            if code in MODIFIER_KEYCODES:             # modifiers: "flags changed" toggles press/release
                is_down = code not in cls._mod_down
                if is_down: cls._mod_down.add(code)
                else: cls._mod_down.discard(code)
            else:
                is_down = event_type == EVENT_KEY_DOWN
            if is_down:
                hide = should_hide(name, cls._swallow, cls._swallow_with_option,
                                   bool(cls._mod_down & OPTION_KEYCODES))
                if hide: cls._swallowed.add(code)
            else:
                hide = code in cls._swallowed
                cls._swallowed.discard(code)
            if not hide:
                return event                           # normal: pynput's own handler takes it from here
            # hidden: pynput's handler won't see it, so tell our watchers ourselves
            if is_down:
                cls._held.add(name)
                for w in list(cls._watchers): w._on_press(name)
            else:
                cls._held.discard(name)
                for w in list(cls._watchers): w._on_release(name)
            return None
        except Exception:
            return event

    # -- start / stop ----------------------------------------------------------
    def start(self) -> bool:
        """Start listening in the background. Returns False (and says why) if it can't."""
        cls = HotkeyWatcher
        if cls._listener is None:
            try:
                from pynput import keyboard
            except ImportError:
                print("Hotkeys off: run  pip install pynput  to use keyboard shortcuts from any app.")
                return False

            def on_press(key):
                name = key_name(key)
                cls._held.add(name)
                for w in list(cls._watchers):
                    w._on_press(name)

            def on_release(key):
                name = key_name(key)
                cls._held.discard(name)
                for w in list(cls._watchers):
                    w._on_release(name)

            try:
                try:
                    listener = keyboard.Listener(on_press=on_press, on_release=on_release,
                                                 darwin_intercept=cls._intercept)
                except TypeError:        # an older pynput without swallowing: listen only
                    print("Note: your pynput can't hide keys from other apps (pip install -U pynput).")
                    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                listener.daemon = True
                listener.start()
            except Exception as problem:      # e.g. permission refused
                print(f"Hotkeys off: {problem}")
                return False
            cls._listener = listener
        cls._watchers.append(self)
        self.ok = True
        return True

    def stop(self) -> None:
        cls = HotkeyWatcher
        if self.ok:
            self.ok = False
            if self in cls._watchers:
                cls._watchers.remove(self)
            if not cls._watchers and cls._listener is not None:
                cls._swallow = frozenset()
                cls._swallow_with_option = frozenset()
                cls._listener.stop()
                cls._listener = None
                cls._held.clear()
                cls._swallowed.clear()
                cls._mod_down.clear()
