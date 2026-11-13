"""
music_tools.py - Rex's music "appendage": the Premium (full tier) Spotify tools.

These talk to Spotify's Web API through spotify_connect.py, so they need CONNECT SPOTIFY done first.
(The basic tier, play / pause / skip for everyone, is spotify.py and doesn't need any of this.)

tools.py lists these on Rex's menu. Each one:
    - returns ONE short sentence saying what happened
    - never crashes: if something goes wrong, the sentence says what

How a tool reaches Spotify:
    music_tools.play_music("Daft Punk", "artist")
        -> _search()          GET  /search             find it
        -> _play()            PUT  /me/player/play     press play on it
        -> spotify_connect.call()  adds the key, sends it, and turns errors into SpotifyError
"""

import difflib
import re
import functools
import subprocess
import threading
import time
import unicodedata

import confirm_box
import indicator
import settings
import spotify
import spotify_connect
from spotify_connect import SpotifyError

APP_PERMISSION = ("FIVES isn't allowed to control the Spotify app yet: System Settings > Privacy & Security > "
                  "Automation, then turn on Spotify for Terminal.")
CONTROLS = {"pause": spotify.pause, "resume": spotify.resume, "skip": spotify.next_track,
            "previous": spotify.previous_song, "restart": spotify.restart}
POPUP_SAID = {"pause": "PAUSED", "resume": "RESUMED", "skip": "SKIPPED TO", "previous": "BACK TO",
              "restart": "STARTED OVER"}
CONTROLS_SAID = {"pause": "Paused", "resume": "Resumed", "skip": "Skipped. Now playing", "previous": "Back to",
                 "restart": "Started over:"}
# The model may pass the user's own word; we translate it. Copying "rewind" is easier for it than mapping it.
ACTION_ALIASES = {"rewind": "restart", "start over": "restart", "run it back": "restart",
                  "play it again": "restart"}
NOT_CONNECTED = "Spotify isn't connected yet. Open FIVES > SETTINGS > CONNECT SPOTIFY first."
# What a person says -> the word Spotify's search uses
KINDS = {"song": "track", "album": "album", "artist": "artist", "playlist": "playlist"}
RECOVER_PAGE = "spotify.com/account/recover-playlists"     # where deleted playlists can be brought back (90 days)
MATCH_CUTOFF = 0.6          # how close a playlist name has to be (0 = anything, 1 = exact) to count as a match
SETTLE_SECONDS = 0.4         # after a skip, the app needs a moment before it reports the new song
CHECK_TRIES = 6              # after pressing play, look this many times to see if music really started...
CHECK_EVERY = 0.25           # ...this many seconds apart (so we wait at most ~1.5s)
WAKE_UP_SECONDS = 10        # how long we wait for the Spotify app to show up after opening it
HIDE_SPOTIFY_SECONDS = 8    # how long after opening Spotify we keep hiding its window (it pops up while loading)
ALEXA_WORDS = {"alexa", "echo", "echo dot"}   # what people call an Amazon speaker
SPEAKER_WORDS = {"speaker", "device"}          # said around a device's name ("the kitchen speaker")
SPOTIFY_BUNDLE_ID = "com.spotify.client"     # macOS's ID for the Spotify app
MAX_PLAYLISTS = 200         # stop reading your playlists after this many (Spotify hands them out 50 at a time)
ADD_LIMIT = 100             # Spotify adds at most 100 songs per request
WORD_CUTOFF = 0.75          # how alike two words must be to count as the same word ("blak" ~ "black")
ENOUGH_WORDS = 0.75         # at least 3/4 of the words you said must appear in the song Spotify found
ORDERS = {"Shuffle": True, "In order": False, "As is": None}    # PLAY ORDER setting -> shuffle
SEARCH_LIMIT = 10           # results to choose from (Spotify's most since 2026)
COVER_WORDS = ("karaoke", "in the style of", "originally performed", "made famous", "tribute",
               "instrumental", "cover", "melody karaoke")          # signs of a copy, not the real song
FILLER_WORDS = {"my", "mine", "the", "a", "an", "playlist", "playlists", "called", "named"}   # not part of a name


# ---- helpers (not tools) ------------------------------------------------------------------------------
def _search(what: str, kind: str, artist: str = "") -> dict | None:
    """The best search result for `what` (by `artist`, if given), or None. kind is song / album / artist / playlist.

    Not just Spotify's #1: karaoke and "in the style of" copies are skipped (unless you asked for one), and if you
    named an artist, it has to be by them. (Spotify's own "artist:" filter stopped working in 2026, so the artist
    goes in as plain words and we check the results ourselves.)"""
    spotify_type = KINDS[kind]
    query = f"{what} {artist}".strip()
    found = spotify_connect.get("/search", q=query, type=spotify_type, limit=SEARCH_LIMIT)
    items = found.get(spotify_type + "s", {}).get("items") or []
    return best_result([item for item in items if item], what, artist)   # Spotify sometimes leaves empty spots


def best_result(items: list[dict], what: str, artist: str = "") -> dict | None:
    """Pick from search results (in Spotify's order). None if nothing fits."""
    real = [item for item in items if not is_a_copy(item, what)] or items     # all copies? then copies it is
    if not artist:
        return real[0] if real else None
    by_them = [item for item in real if by_artist(item, artist)]
    return by_them[0] if by_them else (real[0] if real else None)   # none by them: the tools SAY so (see _instead)


def is_a_copy(item: dict, what: str) -> bool:
    """A karaoke / cover / "in the style of" version? (Unless that's what you asked for: "karaoke get lucky".)"""
    names = " ".join([item.get("name", "")] + [a.get("name", "") for a in item.get("artists") or []]).lower()
    return any(word in names and word not in what.lower() for word in COVER_WORDS)


def _plain(text: str) -> str:
    """'JAŸ-Z' -> 'jayz': no accents, capitals, spaces or symbols, so names compare fairly."""
    no_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", no_accents.lower()) or text.lower().strip()    # (Japanese names stay as is)


def by_artist(item: dict, artist: str) -> bool:
    """Is this by that artist? 'kanye' matches 'Kanye West', 'hiroshi kitadani' matches 'Hiroshi Kitadani'."""
    wanted = _plain(artist)
    for name in [a.get("name", "") for a in item.get("artists") or []]:
        have = _plain(name)
        if wanted in have or have in wanted or difflib.SequenceMatcher(None, wanted, have).ratio() >= WORD_CUTOFF:
            return True
    return False


def _my_playlists() -> list[dict]:
    """Every playlist in your library (up to MAX_PLAYLISTS), as Spotify describes them."""
    playlists = []
    while len(playlists) < MAX_PLAYLISTS:
        page = spotify_connect.get("/me/playlists", limit=50, offset=len(playlists))
        items = [item for item in page.get("items") or [] if item]
        playlists += items
        if not page.get("next") or not items:          # "next" is empty on the last page
            break
    return playlists


def without_filler(text: str) -> str:
    """'my gym playlist' -> 'gym'. Drops words people say AROUND a name that aren't part of it.
    If that leaves nothing ("my playlist"), keep what was said."""
    kept = [word for word in text.split() if word.lower().strip(".,!?'\"") not in FILLER_WORDS]
    return " ".join(kept) or text


def says_mine(text: str) -> bool:
    """Did they say 'my' / 'mine'? Then they mean a playlist in their library, never a stranger's."""
    return any(word in ("my", "mine") for word in _words(text))


def best_name_match(wanted: str, names: list[str]) -> str | None:
    """Pick the name that best matches what was said, or None if nothing is close enough.

    "chill" finds "Chill Vibes 🌙" (it's inside the name), "chil" finds "Chill" (only one letter off),
    and "my gym playlist" finds "Gym" (filler words dropped)."""
    lowered = {name.lower().strip(): name for name in names}
    if wanted.lower().strip() in lowered:               # a name that really is "My Playlist #1"
        return lowered[wanted.lower().strip()]
    wanted = without_filler(wanted).lower().strip()
    if wanted in lowered:                               # exact (ignoring capitals)
        return lowered[wanted]
    inside = [name for low, name in lowered.items() if wanted and wanted in low]
    if inside:
        return min(inside, key=len)                     # "chill" -> prefer "Chill Mix" over "Chill Mix 2019 Old"
    close = difflib.get_close_matches(wanted, list(lowered), n=1, cutoff=MATCH_CUTOFF)
    return lowered[close[0]] if close else None


def _find_my_playlist(name: str) -> tuple[dict | None, list[dict]]:
    """(your playlist that matches `name` or None, all your playlists)."""
    playlists = _my_playlists()
    match = best_name_match(name, [p.get("name", "") for p in playlists])
    found = next((p for p in playlists if p.get("name") == match), None) if match else None
    return found, playlists


def playlist_note() -> str:
    """A line for Rex's prompt listing your playlists, so Rex can match "my workout one" to "⚔️ Conquest ⚔️".
    (The model can't see Spotify, so we tell it.) Empty if Spotify isn't connected or doesn't answer:
    Rex still works without it."""
    if not spotify_connect.connected():
        return ""
    try:
        names = _list_names(_my_playlists())
    except SpotifyError:
        return ""
    return (f"The user's Spotify playlists: {names}. When they mean one of these, pass its exact name.")


def _list_names(playlists: list[dict]) -> str:
    """'Gym, Late Night, Road Trip' (so Rex can guess which one you meant)."""
    names = [p.get("name", "") for p in playlists if p.get("name")]
    return ", ".join(names) if names else "none yet"


def _words(text: str) -> list[str]:
    """'Harder, Better (Live)' -> ['harder', 'better', 'live']"""
    return re.findall(r"[a-z0-9]+", text.lower())


def looks_right(wanted: str, item: dict) -> bool:
    """Is the song Spotify found really what was asked for?

    Spotify's search almost always returns SOMETHING, even for gibberish, so we check: do at least 3/4 of the
    words you said appear (spelling slips are fine) in the song's title and artists?
        "bck in blak"          vs "Back in Black, AC/DC"            -> yes (bck~back, in, blak~black)
        "zzqx not a real song" vs "Sweetness, Elliot James Reay"    -> no"""
    said = _words(wanted)
    found = _words(_describe(item))
    if not said:
        return True
    hits = [word for word in said if word in found or difflib.get_close_matches(word, found, n=1, cutoff=WORD_CUTOFF)]
    return len(hits) >= len(said) * ENOUGH_WORDS


def _describe(item: dict) -> str:
    """'Get Lucky by Daft Punk' for a song, or just the name for anything else."""
    artists = ", ".join(a.get("name", "") for a in item.get("artists") or [])
    return f"{item.get('name', 'something')} by {artists}" if artists else item.get("name", "something")


def _keep_spotify_hidden() -> None:
    """For a few seconds after launch, hide Spotify every time it tries to show its window (like pressing Cmd+H).
    Runs in a background thread so it doesn't slow down finding the device."""
    try:
        from AppKit import NSRunningApplication     # macOS's list of running apps (comes with pyobjc)
    except ImportError:
        return
    deadline = time.time() + HIDE_SPOTIFY_SECONDS
    while time.time() < deadline:
        for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(SPOTIFY_BUNDLE_ID):
            if not app.isHidden():
                app.hide()
        time.sleep(0.1)


def _devices() -> list[dict]:
    """Every place Spotify can play right now (this Mac, an Echo Dot, a phone...)."""
    return spotify_connect.get("/me/player/devices").get("devices") or []


def _mac_name() -> str:
    """This Mac's name (System Settings > General > About). Spotify uses it as the Mac's device name."""
    return subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True).stdout.strip()


def _this_mac(devices: list[dict]) -> dict | None:
    """The Spotify app on THIS Mac, from the device list. None if it isn't open."""
    computers = [d for d in devices if d.get("type") == "Computer"]
    named = [d for d in computers if d.get("name") == _mac_name()]
    return (named or computers or [None])[0]        # another computer is a better guess than a speaker


def _named_device(devices: list[dict], speaker: str) -> dict | None:
    """The device you named ("kitchen", "my phone", "alexa"), or None if nothing matches."""
    wanted = " ".join(w for w in without_filler(speaker).split() if w.lower() not in SPEAKER_WORDS) or speaker
    if wanted.lower().strip() in ALEXA_WORDS:       # people say "Alexa", Spotify says "Hiyu's Echo Dot"
        wanted = "echo"
    name = best_name_match(wanted, [d.get("name", "") for d in devices])
    return next((d for d in devices if d.get("name") == name), None)


def split_speaker(what: str, devices: list[dict]) -> tuple[str, str]:
    """'jingle bells on my echo dot' -> ('jingle bells', 'my echo dot'). A backup, like says_mine: in case Rex
    leaves the speaker inside the song name. Only splits if the end is a REAL device, so 'Lean On Me' stays whole."""
    cut = what.lower().rfind(" on ")                # the LAST " on ", so "Rock On" songs keep their own
    if cut <= 0:
        return what, ""
    song, speaker = what[:cut].strip(), what[cut + len(" on "):].strip()
    if song and _named_device(devices, speaker):
        return song, speaker
    return what, ""


def _send_music_to(speaker: str) -> str:
    """Point Spotify at the right device BEFORE playing: the speaker you named, or else this Mac.
    Without this, Spotify plays wherever you last listened (that's how a song ended up on the Echo Dot).
    Returns "" when ready, or a sentence saying what went wrong."""
    devices = _devices()
    if speaker.strip():
        target = _named_device(devices, speaker)
        if not target:
            names = ", ".join(d.get("name", "?") for d in devices) or "nothing"
            return f"No speaker called '{speaker}'. Spotify can see: {names}."
    else:
        target = _this_mac(devices)
        if not target:
            if not any(d.get("is_active") for d in devices):
                return ""                           # nothing playing anywhere: _on_a_device opens the app here
            mac_id = _wake_spotify()                # something else is playing: open Spotify here first
            if not mac_id:
                return "Couldn't open Spotify on this Mac. Open the Spotify app and try again."
            target = {"id": mac_id}
    if not target.get("is_active"):                 # "transfer playback": move Spotify to that device
        spotify_connect.call("PUT", "/me/player", {"device_ids": [target["id"]], "play": False})
    return ""


def _wake_spotify() -> str | None:
    """Open the Spotify app and wait for it to show up as a device. Returns this Mac's device id, or None."""
    # -g = don't jump to the front, -j = start hidden. Spotify ignores -j and pops up anyway, so we hide it too.
    subprocess.run(["open", "-g", "-j", "-a", "Spotify"], capture_output=True)
    threading.Thread(target=_keep_spotify_hidden, daemon=True).start()
    deadline = time.time() + WAKE_UP_SECONDS
    while time.time() < deadline:
        mac = _this_mac(_devices())                 # wait for THIS Mac, not just any device (like the Echo Dot)
        if mac:
            return mac.get("id")
        time.sleep(1)
    return None


def _on_a_device(action) -> None:
    """Run action(device_id). If Spotify says "no active device" (404), open the app and try once more.

    The Web API can only play on a Spotify app that's awake. This is the #1 way these tools fail."""
    try:
        action(None)                                    # None = "whatever device is already playing"
    except SpotifyError as err:
        if err.status != 404:
            raise
        device_id = _wake_spotify()
        if not device_id:
            raise SpotifyError("Spotify isn't open on any device. Open the Spotify app and try again.")
        action(device_id)


def _with_device(params: dict, device_id: str | None) -> dict:
    """The same params, plus device_id if we have one (a new dictionary; the old one isn't changed)."""
    return {**params, "device_id": device_id} if device_id else params


def _explain(err: SpotifyError) -> str:
    """Turn a SpotifyError into a sentence a person understands."""
    if err.status == 403:
        return "Spotify said no. Playing songs through FIVES needs Spotify Premium."
    if err.status == 401:
        return "Spotify forgot this Mac. Do CONNECT SPOTIFY again in Settings."
    return f"Something went wrong with Spotify: {err}"


# ---- the tools (tools.py puts these on Rex's menu) ------------------------------------------------------
def never_crash(fn):
    """A decorator: wraps a tool so a surprise error comes back as a sentence instead of crashing Rex.
    (A decorator is a function that wraps another one. Writing @never_crash above a def applies it.)"""
    @functools.wraps(fn)                                # keep the tool's name and docstring for Rex's menu
    def safe(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except Exception as err:
            return f"Something unexpected went wrong in {fn.__name__}: {err}"
    return safe


@never_crash
def play_music(what: str, kind: str = "song", shuffle: bool | None = None, mine: bool = False,
               artist: str = "", speaker: str = "") -> str:
    """Play music on Spotify: a song, album, artist, or playlist. Your own playlists are checked first.

    Args:
        what: What to play, without the artist, for example "Get Lucky", "Stand By Me", "Daft Punk", or "gym".
        kind: One of "song", "album", "artist", or "playlist".
        artist: Who it's by, ONLY if the user said an artist ("play USS!! by Hiroshi Kitadani" -> "Hiroshi Kitadani").
            Leave it empty otherwise, even if you think you know who sings it.
        shuffle: True to shuffle, False to play in order. Leave it out unless the user said which.
        mine: True if the user said "my" or "mine" (their own playlist, never one from all of Spotify).
        speaker: Where to play, ONLY if the user named a device ("on my echo dot" -> "my echo dot"). Leave it empty
            otherwise: empty plays on this Mac.
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    kind = kind.lower().strip()
    if kind not in KINDS:
        return f"I can play a song, album, artist, or playlist, not a '{kind}'."
    try:
        if not speaker and " on " in what.lower():     # backup: Rex left "on my echo dot" in the song name
            what, speaker = split_speaker(what, _devices())
        item, everything = _find_my_playlist(what) if kind == "playlist" else (None, [])
        if kind == "playlist" and not item and (mine or says_mine(what)):   # "my" never plays a stranger's playlist
            return f"No playlist called '{without_filler(what)}' in your library. Yours: {_list_names(everything)}."
        item = item or _search(what, kind, artist if kind in ("song", "album") else "")
        if not item:
            return f"Couldn't find a {kind} called '{what}'{_by(artist)} on Spotify."
        if shuffle is None and kind != "song":           # you didn't say: use your PLAY ORDER setting
            shuffle = ORDERS.get(settings.get("play_order"))
        problem = _send_music_to(speaker)
        if problem:
            return problem
        if not _press_play(item, shuffle):
            return (f"Spotify said yes to {_describe(item)}, but nothing started playing. "
                    "Try pressing play in the Spotify app, then ask me again.")
    except SpotifyError as err:
        return _explain(err)
    order = {True: ", shuffled", False: ", in order", None: ""}[shuffle]
    indicator.show(f"{'SHUFFLING' if shuffle else 'PLAYING'} {kind}", item.get("name", what))
    instead = _instead(item, artist) if kind in ("song", "album") else ""
    return f"{instead}{'p' if instead else 'P'}laying {_describe(item)}{order}{' instead' if instead else ''}."


def _start(item: dict, shuffle: bool | None, device_id: str | None) -> None:
    """Set shuffle (if asked), then press play. Shuffle goes first so the very first song is already shuffled."""
    if shuffle is not None:
        try:
            spotify_connect.call("PUT", "/me/player/shuffle", **_with_device({"state": str(shuffle).lower()}, device_id))
        except SpotifyError as err:
            # Spotify sometimes refuses shuffle with 403 "Restriction violated" (seen Nov 2026, Premium account).
            # Shuffle is a nice-to-have, so play anyway. Other errors (like 404 "no device") still count.
            if err.status != 403:
                raise
    # A song is played by itself; an album / artist / playlist is played as a "context" (the whole thing)
    body = {"uris": [item["uri"]]} if item.get("type") == "track" else {"context_uri": item["uri"]}
    spotify_connect.call("PUT", "/me/player/play", body, **_with_device({}, device_id))


def _instead(item: dict, artist: str) -> str:
    """'No version by Taylor Swift, so ' when the pick isn't by the artist asked for (else nothing). Rex sometimes
    fills in an artist on its own, so a wrong guess shouldn't block the song, but you should hear about it."""
    if not artist.strip() or by_artist(item, artist):
        return ""
    return f"No version by {artist}, so "


def _by(artist: str) -> str:
    """' by Daft Punk' (or nothing), for sentences."""
    return f" by {artist}" if artist.strip() else ""


def _wait_for(check) -> bool:
    """Look a few times, a moment apart, until check() is True. False if it never was."""
    for attempt in range(CHECK_TRIES):
        if check():
            return True
        if attempt < CHECK_TRIES - 1:
            time.sleep(CHECK_EVERY)
    return False


def _started(item: dict, before: dict) -> bool:
    """Is what we asked for really playing? Spotify's servers sometimes say "OK!" and the app never starts
    (seen when the app was stopped with nothing loaded), so we check instead of trusting the "OK"."""
    if not spotify.is_running():                        # playing somewhere else (like an Echo Dot): ask the servers
        return bool((spotify_connect.get("/me/player") or {}).get("is_playing"))
    now = spotify.status()
    if now.get("state") != "playing":
        return False
    if item.get("type") == "track":                     # a song: it has to be THAT song
        return now.get("title") == item.get("name")
    return before.get("state") != "playing" or now.get("title") != before.get("title")   # a playlist: it changed


def _press_play(item: dict, shuffle: bool | None) -> bool:
    """Start the music, and make sure it really started. True if it's playing.

    Songs go straight to the Spotify app on this Mac (AppleScript): the servers' "play this one song" says OK but
    STOPS the music (tested Nov 2026, every time). Playlists, albums and artists go through the servers, which
    start on a properly shuffled song; if that doesn't take, the app gets pressed directly."""
    if item.get("type") == "track" and spotify.is_running():
        return _play_in_app(item)
    before = spotify.status() if spotify.is_running() else {}
    _on_a_device(lambda device_id: _start(item, shuffle, device_id))
    return _wait_for(lambda: _started(item, before)) or _play_in_app(item)


def _play_in_app(item: dict) -> bool:
    """Press play in the Spotify app directly (AppleScript), then check it's really playing."""
    if not spotify.is_running() or not spotify.play_uri(item.get("uri", "")):
        return False
    return _wait_for(lambda: _started(item, {}))          # {} = for a playlist, "playing at all" is enough now


@never_crash
def queue_song(what: str, artist: str = "") -> str:
    """Add a song to the end of the Spotify queue (it plays after the current songs).

    Args:
        what: The song, without the artist, for example "Get Lucky".
        artist: Who it's by, ONLY if the user said an artist, for example "Daft Punk". Otherwise leave it empty.
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        song = _search(what, "song", artist)
        if not song:
            return f"Couldn't find a song called '{what}'{_by(artist)} on Spotify."
        _on_a_device(lambda device_id: spotify_connect.call(
            "POST", "/me/player/queue", **_with_device({"uri": song["uri"]}, device_id)))
    except SpotifyError as err:
        return _explain(err)
    instead = _instead(song, artist)
    return f"{instead}{'a' if instead else 'A'}dded {_describe(song)} to the queue{' instead' if instead else ''}."


@never_crash
def now_playing() -> str:
    """Say what song is playing on Spotify right now, who it's by, and what album it's from."""
    if not spotify_connect.connected():                 # no Premium connection: the app still knows
        return _app_now_playing()
    try:
        playing = spotify_connect.get("/me/player/currently-playing")
    except SpotifyError as err:
        return _explain(err)
    item = playing.get("item")
    if not item:                                        # the internet side knows nothing: ask the app itself
        return _app_now_playing()
    album = (item.get("album") or {}).get("name")
    state = "Playing" if playing.get("is_playing") else "Paused on"
    return f"{state} {_describe(item)}" + (f", from {album}." if album else ".")


def _app_now_playing() -> str:
    """What the Spotify APP has in its player bar (AppleScript). Works without Premium or internet, and knows a
    paused song even when Spotify's servers think your Mac is asleep."""
    status = spotify.status()
    if status.get("state") == "error":
        return APP_PERMISSION
    if status.get("state") not in ("playing", "paused"):
        return "Nothing is playing on Spotify right now."
    word = "Playing" if status["state"] == "playing" else "Paused on"
    return f"{word} {_song(status)}."


def _song(status: dict) -> str:
    """'The Most Beautiful Thing by Bruno Major' (or 'the next song' if the app didn't say)."""
    if not status.get("title"):
        return "the next song"
    return f"{status['title']} by {status['artist']}" if status.get("artist") else status["title"]


@never_crash
def music_controls(action: str) -> str:
    """Pause, resume, skip, go back, or start over on what's in the Spotify player right now. Works without Premium.
    You CAN skip: always call this for "skip", "next", "pause", "stop", "back", "rewind", "start over", etc.
    Never say you paused, skipped, went back, or restarted unless you called this tool THIS turn: earlier
    replies in the chat don't count, and saying it without calling it does nothing.

    Args:
        action: One of "pause", "resume", "skip", "previous" (the song before this one), "restart" (this song
            from the beginning), or "rewind" / "run it back" / "play it again" (all the same as restart). Use
            "resume" for "play" / "play the song" when the user didn't name anything. If the user says "rewind",
            "run it back", or "play it again", pass those exact words. Use "previous" only for "back",
            "last song", or "previous song".
    """
    action = action.lower().strip()
    action = ACTION_ALIASES.get(action, action)    # "rewind" -> "restart"
    if action not in CONTROLS:
        return f"I can pause, resume, skip, go back, or start over, not '{action}'."
    status = spotify.status()
    if status.get("state") == "error":
        return APP_PERMISSION
    if status.get("state") == "closed":
        return "Spotify isn't open. Tell me what to play and I'll start it."
    if status.get("state") == "stopped" and action == "resume":
        return "Nothing is loaded in Spotify to resume. Tell me what to play."
    if action == "pause" and status.get("state") == "paused":
        return f"Already paused on {_song(status)}."
    CONTROLS[action]()
    if action in ("skip", "previous"):
        time.sleep(SETTLE_SECONDS)
        status = spotify.status()                       # the song changed: read it again
    indicator.show(POPUP_SAID[action], status.get("title") or "")
    return f"{CONTROLS_SAID[action]} {_song(status)}."


@never_crash
def make_playlist(name: str, songs: list[str]) -> str:
    """Make a new Spotify playlist and fill it with songs. Put any songs the user asked for first.

    Args:
        name: The playlist's name, for example "Rock".
        songs: The songs to put in it, for example ["Thunderstruck by AC/DC", "Back in Black"].
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        found, missing, unsure = _find_songs(songs)
        if not found:
            return f"Didn't make '{name}': couldn't find any of those songs on Spotify." + _unsure_note(unsure)
        playlist = spotify_connect.call("POST", "/me/playlists", {"name": name, "public": False})
        _add_songs(playlist["id"], [song["uri"] for song in found])
    except SpotifyError as err:
        return _explain(err)
    reply = f"Made '{name}' with {len(found)} songs."
    reply += f" Couldn't find: {', '.join(missing)}." if missing else ""
    return reply + _unsure_note(unsure)


def _find_songs(songs: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """Search each song. Returns (songs found, names not found, notes on songs left out because the match
    looked wrong). Left-out songs are NOT added, so a typo never sneaks a random song into your playlist."""
    found, missing, unsure = [], [], []
    for wanted in songs:
        song = _search(wanted, "song")
        if not song:
            missing.append(wanted)
        elif looks_right(wanted, song):
            found.append(song)
        else:
            unsure.append(f"'{wanted}' (best guess: {_describe(song)})")
    return found, missing, unsure


def _unsure_note(unsure: list[str]) -> str:
    """The sentence about left-out songs, so Rex can retry with better words or ask the user."""
    return f" Left out, not sure these are right: {'; '.join(unsure)}." if unsure else ""


def _add_songs(playlist_id: str, uris: list[str]) -> None:
    """Add songs to a playlist, ADD_LIMIT at a time (Spotify's maximum per request)."""
    for start in range(0, len(uris), ADD_LIMIT):
        spotify_connect.call("POST", f"/playlists/{playlist_id}/items", {"uris": uris[start:start + ADD_LIMIT]})


@never_crash
def add_to_playlist(playlist: str, song: str = "") -> str:
    """Add a song to one of the user's own Spotify playlists, found by its name.

    Args:
        playlist: The playlist's name. Close is fine, for example "chill" finds "Chill Vibes".
        song: The song to add. Leave it empty to add the song that's playing right now.
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        target, everything = _find_my_playlist(playlist)
        if not target:
            return f"No playlist called '{playlist}'. Your playlists: {_list_names(everything)}."
        item = _search(song, "song") if song else spotify_connect.get("/me/player/currently-playing").get("item")
        if not item:
            return f"Couldn't find a song called '{song}' on Spotify." if song else "Nothing is playing to add."
        if song and not looks_right(song, item):
            return f"Didn't add anything: not sure '{song}' is {_describe(item)}. Try adding the artist's name."
        _add_songs(target["id"], [item["uri"]])
    except SpotifyError as err:
        return _explain(err)
    return f"Added {_describe(item)} to {target.get('name', playlist)}."


@never_crash
def delete_playlist(playlist: str) -> str:
    """Delete one of the user's Spotify playlists, found by its name. Before anything is deleted, a FIVES box
    pops up on screen and the user types their passcode there. You never need, ask for, or see the passcode.

    Args:
        playlist: The playlist's name. Close is fine, for example "gym" finds "Gym".
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        target, everything = _find_my_playlist(playlist)
        if not target:
            return f"No playlist called '{playlist}'. Your playlists: {_list_names(everything)}."
        name, mine = target.get("name", playlist), _is_mine(target)
        # The box shows the EXACT name, so a wrong fuzzy match gets caught by the person, not deleted
        if not confirm_box.ask(_delete_question(name, target, mine)):
            return f"Didn't delete '{name}': it wasn't confirmed in the passcode box."
        spotify_connect.call("DELETE", "/me/library", uris=target["uri"])
    except SpotifyError as err:
        if err.status == 403:
            return ("Spotify didn't allow deleting. FIVES may need one more permission: "
                    "do CONNECT SPOTIFY again in Settings.")
        return _explain(err)
    if mine:
        return f"Deleted '{name}'. You can get it back for 90 days at {RECOVER_PAGE}."
    return f"Removed '{name}' from your library (it's someone else's playlist, so it still exists for them)."


def _is_mine(playlist: dict) -> bool:
    """Did this person make the playlist? (Otherwise "delete" just unfollows someone else's.)"""
    owner = (playlist.get("owner") or {}).get("id")
    return bool(owner) and owner == spotify_connect.get("/me").get("id")


def _delete_question(name: str, playlist: dict, mine: bool) -> str:
    """What the passcode box asks, for example "Delete 'Gym' (32 songs)? You can recover it for 90 days." """
    # Spotify renamed "tracks" to "items" in 2026; read either
    total = (playlist.get("items") or playlist.get("tracks") or {}).get("total")
    songs = f" ({total} songs)" if isinstance(total, int) else ""
    after = " You can recover it for 90 days." if mine else ""
    return f"Delete '{name}'{songs}?{after}"
