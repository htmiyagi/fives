"""
spotify_connect.py - connect FIVES to someone's Spotify account (Premium), one time, with a walkthrough.

TWO TIERS
    basic   no setup, works for everyone: play / pause / skip / shuffle through the Spotify app (spotify.py)
    full    Premium only, needs this connection: search any song, your playlists by name, make playlists

Why each person makes their own "Spotify app": Spotify gives developer access to Premium accounts only, and one
app may have at most 5 users. So FIVES can't ship one shared key. Instead the walkthrough helps each person make
a free app on THEIR account (about 3 minutes, once).

What the walkthrough does (hub.py draws it; this file is the logic and holds no drawing code):
    1. asks: do you have Premium?
    2. opens Spotify's developer page and says what to click. One thing to paste: the redirect address below.
    3. you copy your new app's Client ID. FIVES watches the clipboard and grabs it.
    4. opens Spotify's own sign-in page. You click Agree. Spotify sends your browser back to a tiny listener
       inside FIVES (the redirect address), which swaps the answer for a key and saves it.

About the key: it is saved in spotify_keys.json next to this file, readable only by you. It never goes to GitHub.
No password is ever seen or stored by FIVES: the sign-in happens on Spotify's page. (This is "PKCE", the sign-in
method made for apps that run on your own computer, so there is no app secret to keep either.)

For the rest of FIVES:
    spotify_connect.tier()            "full" or "basic"
    spotify_connect.get("/me")        ask Spotify's Web API something (refreshes the key by itself when it expires)
    spotify_connect.start()           open the walkthrough (from a button, the tutorial, anywhere)

Try the connection from Terminal after connecting:   python spotify_connect.py
"""

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

KEYS = Path(__file__).resolve().parent / "spotify_keys.json"
PORT = 8754
REDIRECT = f"http://127.0.0.1:{PORT}/callback"       # must be typed into the Spotify app EXACTLY like this
DASHBOARD = "https://developer.spotify.com/dashboard"
AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
WAIT_SECONDS = 300                                   # how long we wait for you to click Agree
# What FIVES asks permission for, all at once, so the music tools never need a second sign-in:
SCOPES = ["user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing",
          "playlist-read-private", "playlist-read-collaborative", "playlist-modify-private",
          "playlist-modify-public", "user-library-read"]


# ---- the saved key ---------------------------------------------------------------------------------
def load_keys() -> dict:
    try:
        return json.loads(KEYS.read_text())
    except (OSError, ValueError):
        return {}


def save_keys(keys: dict) -> None:
    KEYS.write_text(json.dumps(keys, indent=2) + "\n")
    os.chmod(KEYS, 0o600)                            # only you can read it


def connected() -> bool:
    return bool(load_keys().get("refresh_token"))


def tier() -> str:
    return "full" if connected() else "basic"


def who() -> str:
    """The Spotify name we are connected as ("" if not connected)."""
    return load_keys().get("name", "") if connected() else ""


def disconnect() -> None:
    """Forget the key on this Mac. (The Spotify app you made stays on your Spotify account; that's harmless.)"""
    try:
        KEYS.unlink()
    except OSError:
        pass


# ---- talking to Spotify ----------------------------------------------------------------------------
class SpotifyError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status                         # Spotify's HTTP code (404, 403, ...), 0 if we never got one


def _post_token(fields: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(TOKEN, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as reply:
            return json.loads(reply.read())
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read())
        except Exception:
            detail = {}
        why = detail.get("error_description") or detail.get("error") or f"Spotify said no ({err.code})"
        if "client" in str(why).lower():
            why = "Spotify didn't recognise that Client ID. Go back and copy it again from your app's page"
        raise SpotifyError(why)
    except OSError as err:
        raise SpotifyError(f"couldn't reach Spotify ({err})")


def _remember(reply: dict, client_id: str, old: dict) -> dict:
    keys = {**old, "client_id": client_id, "access_token": reply["access_token"],
            "expires_at": time.time() + float(reply.get("expires_in", 3600)),
            "refresh_token": reply.get("refresh_token") or old.get("refresh_token", "")}   # Spotify may send a new one
    save_keys(keys)
    return keys


def token() -> str:
    """A key that works right now. They last an hour; we swap in a fresh one by ourselves when needed."""
    keys = load_keys()
    if not keys.get("refresh_token"):
        raise SpotifyError("Spotify isn't connected yet")
    if keys.get("access_token") and time.time() < keys.get("expires_at", 0) - 60:
        return keys["access_token"]
    reply = _post_token({"grant_type": "refresh_token", "refresh_token": keys["refresh_token"],
                         "client_id": keys["client_id"]})
    return _remember(reply, keys["client_id"], keys)["access_token"]


def get(path: str, **params) -> dict:
    """Ask Spotify's Web API a question, for example get("/search", q="daft punk", type="track", limit=1)."""
    return call("GET", path, **params)


def call(method: str, path: str, body: dict | None = None, **params) -> dict:
    """Tell Spotify's Web API to DO something. method is "PUT" or "POST" (or "GET"), body is sent as JSON.
    For example call("PUT", "/me/player/shuffle", state="true")."""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as reply:
            text = reply.read()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        raise SpotifyError(f"Spotify said no to {path} ({err.code})", err.code)
    except OSError as err:
        raise SpotifyError(f"couldn't reach Spotify ({err})")


# ---- the sign-in (PKCE) ------------------------------------------------------------------------------
def find_client_id(text: str) -> str:
    """A Client ID is exactly 32 letters a-f and digits. Returns it if the text is one (spaces around are fine)."""
    match = re.fullmatch(r"\s*([0-9a-fA-F]{32})\s*", text or "")
    return match.group(1).lower() if match else ""


def new_login(client_id: str):
    """Returns (the address of Spotify's sign-in page, our secret "verifier", a one-time "state" word).

    The verifier is a long random word only we know. We send Spotify its fingerprint (a SHA-256 hash) now, and the
    word itself later with the answer. That proves both steps came from the same program: nobody who merely saw
    the answer fly past could use it."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT, "state": state,
        "scope": " ".join(SCOPES), "code_challenge_method": "S256", "code_challenge": challenge})
    return url, verifier, state


THANKS = ("<html><body style='background:#04122e;color:#dcefff;font-family:-apple-system,sans-serif;"
          "text-align:center;padding-top:18vh'><h1>{title}</h1><p>{line}</p></body></html>")


def wait_for_answer(state: str, cancelled=lambda: False, ready=lambda: None, seconds: float = WAIT_SECONDS) -> str:
    """Listen on the redirect address until Spotify sends the browser back. Returns the one-time code.
    ready() is called once we are listening (that is the moment to open the browser)."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            asked = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(asked.query)
            if asked.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            if query.get("state", [""])[0] != state:
                result["error"] = "that answer wasn't for this sign-in (try again)"
            elif "error" in query:
                result["error"] = ("you pressed Cancel on Spotify's page" if query["error"][0] == "access_denied"
                                   else query["error"][0])
            else:
                result["code"] = query.get("code", [""])[0]
            ok = "code" in result
            page = THANKS.format(title="FIVES is connected to Spotify" if ok else "That didn't work",
                                 line="You can close this tab and go back to FIVES." if ok
                                 else "Go back to FIVES and try again.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode())

        def log_message(self, *args):                # keep the Terminal quiet
            pass

    try:
        server = HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        raise SpotifyError(f"another program is using port {PORT}. Close FIVES completely and try again")
    server.timeout = 0.5
    try:
        ready()
        end = time.time() + seconds
        while not result and time.time() < end and not cancelled():
            server.handle_request()                  # waits up to half a second for the browser
    finally:
        server.server_close()
    if cancelled():
        raise SpotifyError("cancelled")
    if "error" in result:
        raise SpotifyError(result["error"])
    if not result.get("code"):
        raise SpotifyError("didn't hear back from Spotify. If its page said \"Invalid redirect URI\" or "
                           "\"Invalid client\", go back: check the redirect address and copy the Client ID again")
    return result["code"]


def finish_login(client_id: str, code: str, verifier: str) -> dict:
    """Swap the one-time code for the real key, save it, and note the account's name."""
    reply = _post_token({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                         "client_id": client_id, "code_verifier": verifier})
    keys = _remember(reply, client_id, {})
    try:
        me = get("/me")
        keys["name"] = me.get("display_name") or me.get("id") or "your account"
        save_keys(keys)
    except SpotifyError:
        pass
    return keys


# ---- things done on the Mac (swapped out in tests) ----------------------------------------------------
def open_page(url: str) -> None:
    subprocess.run(["open", url])


def copy_text(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode())


def clipboard() -> str:
    try:
        return subprocess.run(["pbpaste"], capture_output=True, timeout=2).stdout.decode(errors="ignore")
    except Exception:
        return ""


# ---- the walkthrough's state (hub.py draws it and calls these when buttons are pressed) -----------------
class Setup:
    step = "closed"      # closed / premium / basic / create / client_id / signin / waiting / done / error
    client_id = ""
    name = ""            # who we connected as
    search_ok = None     # did a test search work? (True / False / None = not tried)
    error = ""
    copied_at = 0.0      # when COPY was last pressed (to flash "COPIED")
    run = 0              # goes up when the walkthrough is closed or restarted, so old background work stops


setup = Setup()
STEP_NUMBER = {"premium": 1, "create": 2, "client_id": 3, "signin": 4, "waiting": 4}


def start() -> None:
    """Open the walkthrough."""
    setup.run += 1
    setup.error, setup.search_ok = "", None
    setup.step = "premium"


def close() -> None:
    setup.run += 1
    setup.step = "closed"


def _watch_clipboard(run: int) -> None:
    """While we wait on the Client ID step: look at the clipboard twice a second."""
    while setup.run == run and setup.step == "client_id":
        found = find_client_id(clipboard())
        if found:
            setup.client_id, setup.step = found, "signin"
            return
        time.sleep(0.5)


def _sign_in(run: int) -> None:
    try:
        url, verifier, state = new_login(setup.client_id)
        code = wait_for_answer(state, cancelled=lambda: setup.run != run, ready=lambda: open_page(url))
        keys = finish_login(setup.client_id, code, verifier)
        if setup.run != run:
            return
        setup.name = keys.get("name", "your account")
        try:                                         # prove the part Premium unlocks: one search
            found = get("/search", q="never gonna give you up", type="track", limit=1)
            setup.search_ok = bool(found.get("tracks", {}).get("items"))
        except SpotifyError:
            setup.search_ok = False
        setup.step = "done"
    except SpotifyError as err:
        if setup.run == run:
            setup.error, setup.step = str(err), "error"
    except Exception as err:                         # never leave the window stuck on "waiting"
        if setup.run == run:
            setup.error, setup.step = f"something unexpected went wrong ({err})", "error"


def press(name: str) -> None:
    """A walkthrough button was pressed."""
    if name == "cancel" or name == "finish":
        close()
    elif name == "yes":
        setup.step = "create"
    elif name == "no":
        setup.step = "basic"
    elif name == "open":
        open_page(DASHBOARD)
    elif name == "copy":
        copy_text(REDIRECT)
        setup.copied_at = time.time()
    elif name == "next":
        copy_text("")                                # so an old Client ID on the clipboard isn't picked up
        setup.step = "client_id"
        threading.Thread(target=_watch_clipboard, args=(setup.run,), daemon=True).start()
    elif name == "signin":
        setup.step = "waiting"
        threading.Thread(target=_sign_in, args=(setup.run,), daemon=True).start()
    elif name == "back":
        setup.run += 1
        setup.step = {"create": "premium", "client_id": "create", "signin": "create", "waiting": "signin",
                      "error": "create", "basic": "premium"}.get(setup.step, "premium")
    elif name == "retry":
        setup.error = ""
        setup.step = "signin" if setup.client_id else "create"


if __name__ == "__main__":
    if not connected():
        raise SystemExit("Not connected yet. Open FIVES > SETTINGS > CONNECT SPOTIFY.")
    print("connected as:", who())
    hit = get("/search", q="never gonna give you up", type="track", limit=1)["tracks"]["items"]
    print("search works:", f"{hit[0]['name']} by {hit[0]['artists'][0]['name']}" if hit else "no result")
