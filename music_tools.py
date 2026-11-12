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
import time

import spotify_connect
from spotify_connect import SpotifyError

NOT_CONNECTED = "Spotify isn't connected yet. Open FIVES > SETTINGS > CONNECT SPOTIFY first."
# What a person says -> the word Spotify's search uses
KINDS = {"song": "track", "album": "album", "artist": "artist", "playlist": "playlist"}
MATCH_CUTOFF = 0.6          # how close a playlist name has to be (0 = anything, 1 = exact) to count as a match
WAKE_UP_SECONDS = 10        # how long we wait for the Spotify app to show up after opening it
MAX_PLAYLISTS = 200         # stop reading your playlists after this many (Spotify hands them out 50 at a time)
ADD_LIMIT = 100             # Spotify adds at most 100 songs per request
WORD_CUTOFF = 0.75          # how alike two words must be to count as the same word ("blak" ~ "black")
ENOUGH_WORDS = 0.75         # at least 3/4 of the words you said must appear in the song Spotify found


# ---- helpers (not tools) ------------------------------------------------------------------------------
def _search(what: str, kind: str) -> dict | None:
    """The first search result for `what`, or None. kind is song / album / artist / playlist."""
    spotify_type = KINDS[kind]
    # For now we just take the FIRST result. (Later: maybe ask "did you mean...?" when results are close.)
    found = spotify_connect.get("/search", q=what, type=spotify_type, limit=1)
    items = found.get(spotify_type + "s", {}).get("items") or []
    items = [item for item in items if item]           # Spotify sometimes puts empty spots in the list
    return items[0] if items else None


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


def best_name_match(wanted: str, names: list[str]) -> str | None:
    """Pick the name that best matches what was said, or None if nothing is close enough.

    "chill" finds "Chill Vibes 🌙" (it's inside the name), and "chil" finds "Chill" (only one letter off)."""
    wanted = wanted.lower().strip()
    lowered = {name.lower().strip(): name for name in names}
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


def _wake_spotify() -> str | None:
    """Open the Spotify app and wait for it to show up as a device. Returns its device id, or None."""
    subprocess.run(["open", "-a", "Spotify"], capture_output=True)
    deadline = time.time() + WAKE_UP_SECONDS
    while time.time() < deadline:
        devices = spotify_connect.get("/me/player/devices").get("devices") or []
        if devices:
            active = [d for d in devices if d.get("is_active")]
            return (active or devices)[0].get("id")
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
def play_music(what: str, kind: str = "song", shuffle: bool | None = None) -> str:
    """Play music on Spotify: a song, album, artist, or playlist. Your own playlists are checked first.

    Args:
        what: What to play, for example "Get Lucky", "Daft Punk", or "my gym playlist".
        kind: One of "song", "album", "artist", or "playlist".
        shuffle: True to shuffle, False to play in order. Leave it out to keep Spotify's current setting.
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    kind = kind.lower().strip()
    if kind not in KINDS:
        return f"I can play a song, album, artist, or playlist, not a '{kind}'."
    try:
        item = _find_my_playlist(what)[0] if kind == "playlist" else None
        item = item or _search(what, kind)
        if not item:
            return f"Couldn't find a {kind} called '{what}' on Spotify."
        _on_a_device(lambda device_id: _start(item, shuffle, device_id))
    except SpotifyError as err:
        return _explain(err)
    order = {True: ", shuffled", False: ", in order", None: ""}[shuffle]
    return f"Playing {_describe(item)}{order}."


def _start(item: dict, shuffle: bool | None, device_id: str | None) -> None:
    """Set shuffle (if asked), then press play. Shuffle goes first so the very first song is already shuffled."""
    if shuffle is not None:
        spotify_connect.call("PUT", "/me/player/shuffle", **_with_device({"state": str(shuffle).lower()}, device_id))
    # A song is played by itself; an album / artist / playlist is played as a "context" (the whole thing)
    body = {"uris": [item["uri"]]} if item.get("type") == "track" else {"context_uri": item["uri"]}
    spotify_connect.call("PUT", "/me/player/play", body, **_with_device({}, device_id))


@never_crash
def queue_song(what: str) -> str:
    """Add a song to the end of the Spotify queue (it plays after the current songs).

    Args:
        what: The song, for example "Get Lucky" or "Get Lucky by Daft Punk".
    """
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        song = _search(what, "song")
        if not song:
            return f"Couldn't find a song called '{what}' on Spotify."
        _on_a_device(lambda device_id: spotify_connect.call(
            "POST", "/me/player/queue", **_with_device({"uri": song["uri"]}, device_id)))
    except SpotifyError as err:
        return _explain(err)
    return f"Added {_describe(song)} to the queue."


@never_crash
def now_playing() -> str:
    """Say what song is playing on Spotify right now, who it's by, and what album it's from."""
    if not spotify_connect.connected():
        return NOT_CONNECTED
    try:
        playing = spotify_connect.get("/me/player/currently-playing")
    except SpotifyError as err:
        return _explain(err)
    item = playing.get("item")
    if not item:                                        # empty answer = nothing playing
        return "Nothing is playing on Spotify right now."
    album = (item.get("album") or {}).get("name")
    state = "Playing" if playing.get("is_playing") else "Paused on"
    return f"{state} {_describe(item)}" + (f", from {album}." if album else ".")


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
