"""
google_connect.py - connect FIVES to someone's Google Calendar, once, with a short walkthrough.

Unlike Spotify, nobody has to make their own app here: FIVES ships ONE Google sign-in client (Hoyu's Google
project, the same one ECHO Calendar uses), so connecting is just "sign in with Google, click Allow".

What the walkthrough does (hub.py draws it; this file is the logic and holds no drawing code):
    1. explains the one odd screen: Google says "Google hasn't verified this app". That's expected (the project is
       published but not reviewed by Google, which is what lets everyone stay signed in). Click Advanced, then Go to.
    2. opens Google's own sign-in page. You pick your account and click Continue. Google sends your browser back to a
       tiny listener inside FIVES (on 127.0.0.1, this Mac only), which swaps the answer for a key and saves it.
    3. shows who you're connected as, and how many events you have this week (proof it works).

About the key: a "refresh token", saved in google_keys.json next to this file, readable only by you, never on
GitHub. It doesn't expire on its own, so you connect ONCE. FIVES never sees your password. Sign-in is "PKCE", the
method made for apps on your own computer (same as spotify_connect.py).

The client secret below is not really a secret: Google says so for desktop apps, because anyone can open the app
and read it. The real protection is that YOU must click Allow, and the key that gives access stays on your Mac.

For the rest of FIVES:
    google_connect.connected()            True once signed in
    google_connect.needs_reconnect()      True if Google cancelled the key (then show a RECONNECT button)
    google_connect.who()                  the Google email we're connected as ("" if not connected)
    google_connect.call("GET", "/calendars/primary/events", maxResults=5)    ask Google Calendar something
    google_connect.start(switch=False)    open the walkthrough (switch=True: let them pick a different account)

Try the connection from Terminal after connecting:   python google_connect.py
"""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Hoyu's "Desktop app" client (Google Cloud > Google Auth Platform > Clients > F.I.V.E.S.). Paste both in once.
CLIENT_ID = ""
CLIENT_SECRET = ""

KEYS = Path(__file__).resolve().parent / "google_keys.json"
PORT = 8755                                          # Spotify's listener uses 8754
REDIRECT = f"http://127.0.0.1:{PORT}"                # desktop clients accept any 127.0.0.1 port, nothing to register
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOKE = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events"   # see, add, change and delete events. Nothing else.
WAIT_SECONDS = 300                                   # how long we wait for you to click Allow
WEEK = timedelta(days=7)                             # the "you have N events this week" check at the end


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


def needs_reconnect() -> bool:
    """Google cancelled the key (you removed FIVES in your Google account, or changed your password)."""
    return connected() and bool(load_keys().get("expired"))


def who() -> str:
    """The Google email we are connected as ("" if not connected)."""
    return load_keys().get("email", "") if connected() else ""


def disconnect(revoke: bool = True) -> None:
    """Forget the key on this Mac, and tell Google to cancel it too (in the background, so it never blocks).
    revoke=False only forgets it: SWITCH ACCOUNT uses that, because cancelling at Google could also cancel the
    brand-new sign-in if you picked the same account again."""
    refresh = load_keys().get("refresh_token", "")
    try:
        KEYS.unlink()
    except OSError:
        pass
    if refresh and revoke:
        threading.Thread(target=_revoke, args=(refresh,), daemon=True).start()


def _revoke(refresh: str) -> None:
    body = urllib.parse.urlencode({"token": refresh}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(REVOKE, data=body), timeout=10).close()
    except OSError:
        pass                                         # offline: the key is gone from this Mac anyway


# ---- talking to Google -----------------------------------------------------------------------------
class GoogleError(Exception):
    def __init__(self, message: str, status: int = 0, expired: bool = False):
        super().__init__(message)
        self.status = status                         # Google's HTTP code (404, 403, ...), 0 if we never got one
        self.expired = expired                       # True: the key was cancelled, the person must reconnect


def _post_token(fields: dict) -> dict:
    fields = {**fields, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(TOKEN, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as reply:
            return json.loads(reply.read())
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read())
        except ValueError:
            detail = {}
        if detail.get("error") == "invalid_grant":   # the key was cancelled or expired
            raise GoogleError("Google signed FIVES out. Press RECONNECT and sign in again", err.code, expired=True)
        why = detail.get("error_description") or detail.get("error") or f"Google said no ({err.code})"
        raise GoogleError(why, err.code)
    except OSError as err:
        raise GoogleError(f"couldn't reach Google ({err})")


def _remember(reply: dict, old: dict) -> dict:
    keys = {**old, "access_token": reply["access_token"],
            "expires_at": time.time() + float(reply.get("expires_in", 3600)),
            "refresh_token": reply.get("refresh_token") or old.get("refresh_token", "")}
    keys.pop("expired", None)
    save_keys(keys)
    return keys


def token() -> str:
    """A key that works right now. They last an hour; we swap in a fresh one by ourselves when needed."""
    keys = load_keys()
    if not keys.get("refresh_token"):
        raise GoogleError("Google Calendar isn't connected yet. Open SETTINGS > GOOGLE CALENDAR")
    if keys.get("access_token") and time.time() < keys.get("expires_at", 0) - 60:
        return keys["access_token"]
    try:
        reply = _post_token({"grant_type": "refresh_token", "refresh_token": keys["refresh_token"]})
    except GoogleError as err:
        if err.expired:
            save_keys({**keys, "expired": True})     # so Settings can show RECONNECT
        raise
    return _remember(reply, keys)["access_token"]


def call(method: str, path: str, body: dict | None = None, **params) -> dict:
    """Ask Google Calendar's API something, e.g. call("GET", "/calendars/primary/events", maxResults=5).
    method is "GET", "POST" (add) or "DELETE". body is sent as JSON."""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as reply:
            text = reply.read()
    except urllib.error.HTTPError as err:
        raise GoogleError(f"Google Calendar said no to {path} ({err.code})", err.code)
    except OSError as err:
        raise GoogleError(f"couldn't reach Google ({err})")
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


# ---- the sign-in (PKCE) ------------------------------------------------------------------------------
def new_login(switch: bool = False):
    """Returns (the address of Google's sign-in page, our secret "verifier", a one-time "state" word).

    Same idea as spotify_connect.new_login: we send Google the verifier's fingerprint now and the verifier itself
    later, which proves both steps came from this program.
    access_type=offline asks for the long-lasting refresh token; prompt=consent makes Google send one every time
    (it skips it on a repeat sign-in otherwise). switch=True also shows Google's account picker."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT, "state": state,
        "scope": SCOPE, "access_type": "offline", "prompt": "select_account consent" if switch else "consent",
        "code_challenge_method": "S256", "code_challenge": challenge})
    return url, verifier, state


THANKS = ("<html><body style='background:#04122e;color:#dcefff;font-family:-apple-system,sans-serif;"
          "text-align:center;padding-top:18vh'><h1>{title}</h1><p>{line}</p></body></html>")


def read_answer(path: str, state: str) -> dict:
    """What Google's redirect said: {"code": ...} or {"error": ...}. {} if it isn't our sign-in page at all."""
    asked = urllib.parse.urlparse(path)
    if asked.path not in ("", "/"):
        return {}
    query = urllib.parse.parse_qs(asked.query)
    if query.get("state", [""])[0] != state:
        return {"error": "that answer wasn't for this sign-in (try again)"}
    if "error" in query:
        return {"error": "you pressed Cancel on Google's page" if query["error"][0] == "access_denied"
                else query["error"][0]}
    if SCOPE not in query.get("scope", [""])[0].split():
        return {"error": "the calendar box wasn't ticked on Google's page. Sign in again and tick it"}
    return {"code": query.get("code", [""])[0]}


def wait_for_answer(state: str, cancelled=lambda: False, ready=lambda: None, seconds: float = WAIT_SECONDS) -> str:
    """Listen on 127.0.0.1 until Google sends the browser back. Returns the one-time code.
    ready() is called once we are listening (that is the moment to open the browser)."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            answer = read_answer(self.path, state)
            if not answer:                           # the browser asking for /favicon.ico and such
                self.send_response(404)
                self.end_headers()
                return
            result.update(answer)
            ok = "code" in answer
            page = THANKS.format(title="FIVES is connected to Google Calendar" if ok else "That didn't work",
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
        raise GoogleError(f"another program is using port {PORT}. Close FIVES completely and try again")
    server.timeout = 0.5
    try:
        ready()
        end = time.time() + seconds
        while not result and time.time() < end and not cancelled():
            server.handle_request()                  # waits up to half a second for the browser
    finally:
        server.server_close()
    if cancelled():
        raise GoogleError("cancelled")
    if "error" in result:
        raise GoogleError(result["error"])
    if not result.get("code"):
        raise GoogleError("didn't hear back from Google in 5 minutes")
    return result["code"]


def finish_login(code: str, verifier: str) -> dict:
    """Swap the one-time code for the real key, save it, and note the account's email."""
    reply = _post_token({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                         "code_verifier": verifier})
    keys = _remember(reply, {})
    try:
        keys["email"] = call("GET", "/calendars/primary").get("id", "")   # your main calendar's id IS your email
        save_keys(keys)
    except GoogleError:
        pass
    return keys


def events_this_week() -> int:
    """How many events are on the main calendar in the next 7 days (the walkthrough's proof that it works)."""
    now = datetime.now(timezone.utc)
    found = call("GET", "/calendars/primary/events", timeMin=now.isoformat(), timeMax=(now + WEEK).isoformat(),
                 singleEvents="true", maxResults=250)
    return len(found.get("items", []))


# ---- things done on the Mac (swapped out in tests) ----------------------------------------------------
def open_page(url: str) -> None:
    subprocess.run(["open", url])


# ---- the walkthrough's state (hub.py draws it and calls these when buttons are pressed) -----------------
class Setup:
    step = "closed"      # closed / intro / waiting / done / error
    switch = False       # True: SWITCH ACCOUNT (show Google's account picker)
    email = ""           # who we connected as
    events = None        # how many events this week (None = couldn't check)
    error = ""
    run = 0              # goes up when the walkthrough is closed or restarted, so old background work stops


setup = Setup()


def start(switch: bool = False) -> None:
    """Open the walkthrough. switch=True is SWITCH ACCOUNT: same steps, plus Google's account picker."""
    setup.run += 1
    setup.switch, setup.error, setup.events = switch, "", None
    setup.step = "intro" if CLIENT_ID and CLIENT_SECRET else "error"
    if setup.step == "error":
        setup.error = "this copy of FIVES has no Google sign-in client yet (CLIENT_ID in google_connect.py)"


def close() -> None:
    setup.run += 1
    setup.step = "closed"


def _sign_in(run: int) -> None:
    try:
        url, verifier, state = new_login(setup.switch)
        code = wait_for_answer(state, cancelled=lambda: setup.run != run, ready=lambda: open_page(url))
        if setup.switch:
            disconnect(revoke=False)                 # only now: a cancelled switch keeps the old account
        keys = finish_login(code, verifier)
        if setup.run != run:
            return
        setup.email = keys.get("email", "")
        try:
            setup.events = events_this_week()
        except GoogleError:
            setup.events = None
        setup.step = "done"
    except GoogleError as err:
        if setup.run == run:
            setup.error, setup.step = str(err), "error"
    except Exception as err:                         # never leave the window stuck on "waiting"
        if setup.run == run:
            setup.error, setup.step = f"something unexpected went wrong ({err})", "error"


def press(name: str) -> None:
    """A walkthrough button was pressed."""
    if name in ("cancel", "finish"):
        close()
    elif name == "signin":
        setup.step = "waiting"
        threading.Thread(target=_sign_in, args=(setup.run,), daemon=True).start()
    elif name in ("back", "retry"):
        setup.run += 1                               # stops a sign-in that's still waiting
        setup.error = ""
        start(setup.switch)


if __name__ == "__main__":
    if not connected():
        raise SystemExit("Not connected yet. Open FIVES > SETTINGS > GOOGLE CALENDAR > CONNECT.")
    try:
        print(f"Connected as {who() or 'an unknown account'}. Events in the next 7 days: {events_this_week()}")
    except GoogleError as err:
        raise SystemExit(f"Connected, but: {err}")
