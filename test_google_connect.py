"""
Tests for google_connect.py (the Google Calendar sign-in), with no internet and no real Google account.

Run them:   .venv/bin/python -m unittest test_google_connect -v

The key file is pointed at a throwaway folder, so your real google_keys.json is never touched. Every call that
would reach Google (_post_token, urlopen, open_page) is swapped for a fake with mock.patch.
"""

import json
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import google_connect as gc
from google_connect import GoogleError


class TempKeys(unittest.TestCase):
    """Base class: a throwaway key file and a pretend client, so tests never touch the real ones."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, value in (("KEYS", Path(folder.name) / "google_keys.json"),
                            ("CLIENT_ID", "test-client.apps.googleusercontent.com"), ("CLIENT_SECRET", "test-secret")):
            patcher = mock.patch.object(gc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        no_revoke = mock.patch.object(gc, "_revoke")          # never call Google's real revoke page
        self.revoke = no_revoke.start()
        self.addCleanup(no_revoke.stop)
        gc.setup.step = "closed"


class SavedKey(TempKeys):
    def test_not_connected_at_first(self):
        self.assertFalse(gc.connected())
        self.assertEqual(gc.who(), "")

    def test_connected_shows_the_email(self):
        gc.save_keys({"refresh_token": "r", "email": "student@example.com"})
        self.assertTrue(gc.connected())
        self.assertEqual(gc.who(), "student@example.com")

    def test_key_file_is_private(self):
        gc.save_keys({"refresh_token": "r"})
        self.assertEqual(gc.KEYS.stat().st_mode & 0o777, 0o600)

    def test_disconnect_forgets_and_cancels_at_google(self):
        gc.save_keys({"refresh_token": "r"})
        gc.disconnect()
        time.sleep(0.05)                                      # the cancel runs in the background
        self.assertFalse(gc.connected())
        self.revoke.assert_called_once_with("r")

    def test_switching_only_forgets(self):
        gc.save_keys({"refresh_token": "r"})
        gc.disconnect(revoke=False)
        time.sleep(0.05)
        self.assertFalse(gc.connected())
        self.revoke.assert_not_called()


class FreshKey(TempKeys):
    def test_a_key_that_still_works_is_reused(self):
        gc.save_keys({"refresh_token": "r", "access_token": "a", "expires_at": time.time() + 600})
        with mock.patch.object(gc, "_post_token") as post:
            self.assertEqual(gc.token(), "a")
        post.assert_not_called()

    def test_an_old_key_is_swapped_for_a_new_one(self):
        gc.save_keys({"refresh_token": "r", "access_token": "old", "expires_at": 0, "email": "e@x.com"})
        with mock.patch.object(gc, "_post_token", return_value={"access_token": "new", "expires_in": 3600}):
            self.assertEqual(gc.token(), "new")
        keys = gc.load_keys()
        self.assertEqual((keys["refresh_token"], keys["email"]), ("r", "e@x.com"))   # kept what Google didn't resend

    def test_a_cancelled_key_asks_for_reconnect(self):
        gc.save_keys({"refresh_token": "r", "expires_at": 0})
        cancelled = GoogleError("signed out", 400, expired=True)
        with mock.patch.object(gc, "_post_token", side_effect=cancelled):
            with self.assertRaises(GoogleError) as caught:
                gc.token()
        self.assertTrue(caught.exception.expired)
        self.assertTrue(gc.needs_reconnect())

    def test_signing_in_again_clears_reconnect(self):
        gc.save_keys({"refresh_token": "r", "expired": True})
        gc._remember({"access_token": "a", "refresh_token": "r2"}, gc.load_keys())
        self.assertFalse(gc.needs_reconnect())

    def test_not_connected_gives_a_clear_message(self):
        with self.assertRaises(GoogleError) as caught:
            gc.token()
        self.assertIn("isn't connected", str(caught.exception))


class SignInPage(TempKeys):
    def test_asks_for_calendar_events_only_and_a_lasting_key(self):
        url, verifier, state = gc.new_login()
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["scope"], [gc.SCOPE])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["consent"])
        self.assertEqual(query["state"], [state])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn(verifier, url)                       # only the fingerprint goes out, never the verifier

    def test_switch_shows_the_account_picker(self):
        url, _, _ = gc.new_login(switch=True)
        self.assertIn("select_account", urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["prompt"][0])


class GooglesAnswer(unittest.TestCase):
    def answer(self, **query):
        return gc.read_answer("/?" + urllib.parse.urlencode(query), "S")

    def test_good_answer_gives_the_code(self):
        self.assertEqual(self.answer(state="S", code="C", scope=gc.SCOPE), {"code": "C"})

    def test_answer_for_another_sign_in_is_refused(self):
        self.assertIn("error", self.answer(state="X", code="C", scope=gc.SCOPE))

    def test_cancel_on_googles_page(self):
        self.assertIn("Cancel", self.answer(state="S", error="access_denied")["error"])

    def test_calendar_box_not_ticked(self):
        self.assertIn("ticked", self.answer(state="S", code="C", scope="openid")["error"])

    def test_other_pages_are_ignored(self):
        self.assertEqual(gc.read_answer("/favicon.ico", "S"), {})


class Walkthrough(TempKeys):
    def test_opens_on_the_intro(self):
        gc.start()
        self.assertEqual(gc.setup.step, "intro")

    def test_without_a_client_it_says_so_instead_of_breaking(self):
        with mock.patch.object(gc, "CLIENT_ID", ""):
            gc.start()
        self.assertEqual(gc.setup.step, "error")
        self.assertIn("CLIENT_ID", gc.setup.error)

    def test_back_from_waiting_goes_to_intro_and_stops_the_sign_in(self):
        gc.start()
        gc.setup.step = "waiting"
        run = gc.setup.run
        gc.press("back")
        self.assertEqual(gc.setup.step, "intro")
        self.assertNotEqual(gc.setup.run, run)

    def test_full_sign_in_with_fake_google(self):
        def fake_post(fields):
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        def fake_call(method, path, body=None, **params):
            return {"id": "student@example.com"} if path == "/calendars/primary" else {"items": [{}, {}, {}]}

        gc.start()
        with mock.patch.object(gc, "wait_for_answer", return_value="CODE"), \
                mock.patch.object(gc, "_post_token", side_effect=fake_post), \
                mock.patch.object(gc, "call", side_effect=fake_call), \
                mock.patch.object(gc, "open_page"):
            gc._sign_in(gc.setup.run)
        self.assertEqual(gc.setup.step, "done")
        self.assertEqual((gc.setup.email, gc.setup.events), ("student@example.com", 3))
        self.assertEqual(gc.who(), "student@example.com")

    def test_a_cancelled_switch_keeps_the_old_account(self):
        gc.save_keys({"refresh_token": "old", "email": "old@example.com"})
        gc.start(switch=True)
        with mock.patch.object(gc, "wait_for_answer", side_effect=GoogleError("you pressed Cancel")):
            gc._sign_in(gc.setup.run)
        self.assertEqual(gc.setup.step, "error")
        self.assertEqual(gc.who(), "old@example.com")


class CallingGoogle(TempKeys):
    def test_key_swap_sends_the_client_id_and_secret(self):
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = b'{"access_token": "a"}'
        with mock.patch("urllib.request.urlopen", return_value=reply) as opened:
            gc._post_token({"grant_type": "refresh_token", "refresh_token": "r"})
        sent = urllib.parse.parse_qs(opened.call_args[0][0].data.decode())
        self.assertEqual((sent["client_id"], sent["client_secret"]), ([gc.CLIENT_ID], ["test-secret"]))

    def test_errors_become_a_sentence_not_a_crash(self):
        gc.save_keys({"refresh_token": "r", "access_token": "a", "expires_at": time.time() + 600})
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no internet")):
            with self.assertRaises(GoogleError) as caught:
                gc.call("GET", "/calendars/primary")
        self.assertIn("couldn't reach Google", str(caught.exception))

    def test_sends_the_key_and_reads_json(self):
        gc.save_keys({"refresh_token": "r", "access_token": "a", "expires_at": time.time() + 600})
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({"id": "x"}).encode()
        with mock.patch("urllib.request.urlopen", return_value=reply) as opened:
            self.assertEqual(gc.call("GET", "/calendars/primary"), {"id": "x"})
        self.assertEqual(opened.call_args[0][0].get_header("Authorization"), "Bearer a")


if __name__ == "__main__":
    unittest.main()
