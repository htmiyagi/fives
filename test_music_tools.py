"""
Tests for music_tools.py, with a FAKE Spotify, so they run without your account or the internet.

Run them:   .venv/bin/python -m unittest test_music_tools -v

How the fake works: `mock.patch` swaps spotify_connect.get / call / connected for our own functions while a test
runs, then puts the real ones back. Every request the tools make is written down in `self.sent`, so a test can
check exactly what would have been sent to Spotify.
"""

import unittest
from unittest import mock

import music_tools
import spotify_connect
from spotify_connect import SpotifyError

GET_LUCKY = {"type": "track", "uri": "spotify:track:lucky", "name": "Get Lucky",
             "artists": [{"name": "Daft Punk"}], "album": {"name": "Random Access Memories"}}
GYM = {"id": "gym1", "uri": "spotify:playlist:gym1", "type": "playlist", "name": "Gym"}
CHILL = {"id": "chill1", "uri": "spotify:playlist:chill1", "type": "playlist", "name": "Chill Vibes"}


class FakeSpotify(unittest.TestCase):
    """Base class: sets up the fake. Each test fills in self.answers (what GET requests return)."""

    def setUp(self):
        self.sent = []                                   # every (method, path, body, params) the tools sent
        self.searched = []                               # every GET path the tools asked for
        self.answers = {"/me/playlists": {"items": [GYM, CHILL], "next": None}}
        self.songs = {"get lucky": GET_LUCKY}            # what the fake search can find
        self.fail_next_play_with = None                  # set to 404 to pretend no device is awake
        for name, fake in (("get", self.fake_get), ("call", self.fake_call), ("connected", lambda: True)):
            patcher = mock.patch(f"spotify_connect.{name}", fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_get(self, path, **params):
        self.searched.append(path)                       # every GET path, so tests can check what was looked up
        if path == "/search":
            song = self.songs.get(params["q"].lower())
            return {"tracks": {"items": [song] if song else []}}
        return self.answers.get(path, {})

    def fake_call(self, method, path, body=None, **params):
        self.sent.append((method, path, body, params))
        if path == "/me/player/play" and self.fail_next_play_with:
            status, self.fail_next_play_with = self.fail_next_play_with, None
            raise SpotifyError("no device", status)
        if path == "/me/playlists":
            return {"id": "new1"}
        return {}


class PlayMusicTests(FakeSpotify):
    def test_plays_a_song_by_its_uri(self):
        reply = music_tools.play_music("Get Lucky", "song")
        self.assertEqual(reply, "Playing Get Lucky by Daft Punk.")
        self.assertEqual(self.sent, [("PUT", "/me/player/play", {"uris": ["spotify:track:lucky"]}, {})])

    def test_my_playlist_is_found_by_a_close_name_and_shuffled_first(self):
        reply = music_tools.play_music("chil", "playlist", shuffle=True)
        self.assertEqual(reply, "Playing Chill Vibes, shuffled.")
        self.assertEqual(self.sent[0], ("PUT", "/me/player/shuffle", None, {"state": "true"}))
        self.assertEqual(self.sent[1][2], {"context_uri": "spotify:playlist:chill1"})

    def test_in_order_turns_shuffle_off(self):
        music_tools.play_music("gym", "playlist", shuffle=False)
        self.assertEqual(self.sent[0][3], {"state": "false"})

    def test_wakes_spotify_and_retries_when_no_device_is_active(self):
        self.fail_next_play_with = 404
        self.answers["/me/player/devices"] = {"devices": [{"id": "mac", "is_active": False}]}
        with mock.patch("music_tools.subprocess.run"):   # don't really open the Spotify app
            reply = music_tools.play_music("Get Lucky")
        self.assertEqual(reply, "Playing Get Lucky by Daft Punk.")
        self.assertEqual(self.sent[-1][3], {"device_id": "mac"})

    def test_my_playlist_with_filler_words_plays_yours(self):
        reply = music_tools.play_music("my gym playlist", "playlist", shuffle=True)
        self.assertEqual(reply, "Playing Gym, shuffled.")

    def test_my_never_falls_back_to_a_strangers_playlist(self):
        reply = music_tools.play_music("my road trip playlist", "playlist")
        self.assertEqual(reply, "No playlist called 'road trip' in your library. Yours: Gym, Chill Vibes.")
        self.assertFalse(any(path == "/search" for path in self.searched), "it searched all of Spotify")
        self.assertEqual(self.sent, [])                          # nothing was played

    def test_mine_checkbox_works_even_when_rex_drops_the_word_my(self):   # Rex really did drop it in testing
        reply = music_tools.play_music("road trip playlist", "playlist", mine=True)
        self.assertIn("in your library", reply)
        self.assertNotIn("/search", self.searched)

    def test_without_my_it_can_search_all_of_spotify(self):
        music_tools.play_music("a road trip playlist", "playlist")
        self.assertIn("/search", self.searched)

    def test_playlist_note_tells_rex_your_playlist_names(self):
        self.assertIn("Gym, Chill Vibes", music_tools.playlist_note())

    def test_playlist_note_is_empty_when_spotify_is_not_connected(self):
        with mock.patch("spotify_connect.connected", lambda: False):
            self.assertEqual(music_tools.playlist_note(), "")

    def test_playlist_note_is_empty_when_spotify_fails(self):
        with mock.patch("spotify_connect.get", side_effect=SpotifyError("down", 500)):
            self.assertEqual(music_tools.playlist_note(), "")

    def test_says_when_nothing_is_found(self):
        self.assertIn("Couldn't find", music_tools.play_music("asdfgh", "song"))

    def test_rejects_an_unknown_kind(self):
        self.assertIn("not a 'podcast'", music_tools.play_music("x", "podcast"))

    def test_premium_error_becomes_a_sentence(self):
        self.fail_next_play_with = 403
        self.assertIn("Premium", music_tools.play_music("Get Lucky"))


class OtherToolTests(FakeSpotify):
    def test_queue_song(self):
        self.assertEqual(music_tools.queue_song("get lucky"), "Added Get Lucky by Daft Punk to the queue.")
        self.assertEqual(self.sent, [("POST", "/me/player/queue", None, {"uri": "spotify:track:lucky"})])

    def test_now_playing(self):
        self.answers["/me/player/currently-playing"] = {"is_playing": True, "item": GET_LUCKY}
        self.assertEqual(music_tools.now_playing(),
                         "Playing Get Lucky by Daft Punk, from Random Access Memories.")

    def test_now_playing_when_nothing_plays(self):
        self.assertEqual(music_tools.now_playing(), "Nothing is playing on Spotify right now.")

    def test_make_playlist_reports_songs_it_could_not_find(self):
        reply = music_tools.make_playlist("Rock", ["Get Lucky", "Bck in Blak"])
        self.assertEqual(reply, "Made 'Rock' with 1 songs. Couldn't find: Bck in Blak.")
        self.assertEqual(self.sent[-1], ("POST", "/playlists/new1/items", {"uris": ["spotify:track:lucky"]}, {}))

    def test_make_playlist_makes_nothing_if_no_songs_are_found(self):
        self.assertIn("Didn't make", music_tools.make_playlist("Rock", ["zzzz"]))
        self.assertEqual(self.sent, [])

    def test_add_current_song_to_playlist_by_close_name(self):
        self.answers["/me/player/currently-playing"] = {"item": GET_LUCKY}
        self.assertEqual(music_tools.add_to_playlist("chill"), "Added Get Lucky by Daft Punk to Chill Vibes.")

    def test_unknown_playlist_lists_yours_so_rex_can_guess(self):
        self.assertEqual(music_tools.add_to_playlist("road trip", "get lucky"),
                         "No playlist called 'road trip'. Your playlists: Gym, Chill Vibes.")

    def test_a_surprise_error_becomes_a_sentence_not_a_crash(self):
        with mock.patch("spotify_connect.get", side_effect=KeyError("uri")):
            self.assertIn("Something unexpected went wrong in now_playing", music_tools.now_playing())

    def test_every_tool_asks_you_to_connect_first(self):
        with mock.patch("spotify_connect.connected", lambda: False):
            for reply in (music_tools.play_music("x"), music_tools.queue_song("x"), music_tools.now_playing(),
                          music_tools.make_playlist("x", ["y"]), music_tools.add_to_playlist("x")):
                self.assertEqual(reply, music_tools.NOT_CONNECTED)


class DeletePlaylistTests(FakeSpotify):
    def setUp(self):
        super().setUp()
        self.mine = {**GYM, "owner": {"id": "hoyu"}, "items": {"total": 32}}
        self.theirs = {**CHILL, "owner": {"id": "someone_else"}, "items": {"total": 50}}
        self.answers["/me/playlists"] = {"items": [self.mine, self.theirs], "next": None}
        self.answers["/me"] = {"id": "hoyu"}
        self.asked = []                                     # every question the (fake) passcode box was asked
        self.box_says = True

        def fake_ask(question):
            self.asked.append(question)
            return self.box_says
        patcher = mock.patch("music_tools.confirm_box.ask", fake_ask)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deletes_only_after_the_box_says_yes(self):
        reply = music_tools.delete_playlist("gim")                       # a typo still finds "Gym"
        self.assertEqual(self.asked, ["Delete 'Gym' (32 songs)? You can recover it for 90 days."])
        self.assertEqual(self.sent, [("DELETE", "/me/library", None, {"uris": "spotify:playlist:gym1"})])
        self.assertIn("Deleted 'Gym'. You can get it back for 90 days", reply)

    def test_nothing_is_deleted_when_the_box_says_no(self):
        self.box_says = False
        reply = music_tools.delete_playlist("gym")
        self.assertEqual(reply, "Didn't delete 'Gym': it wasn't confirmed in the passcode box.")
        self.assertEqual(self.sent, [])

    def test_unknown_playlist_never_opens_the_box(self):
        reply = music_tools.delete_playlist("road trip")
        self.assertIn("No playlist called 'road trip'", reply)
        self.assertEqual((self.asked, self.sent), ([], []))

    def test_someone_elses_playlist_is_only_unfollowed(self):
        reply = music_tools.delete_playlist("chill vibes")
        self.assertEqual(self.asked, ["Delete 'Chill Vibes' (50 songs)?"])  # no "recover": it isn't yours
        self.assertIn("Removed 'Chill Vibes' from your library", reply)

    def test_missing_permission_says_how_to_fix_it(self):
        with mock.patch("spotify_connect.call", side_effect=SpotifyError("no", 403)):
            self.assertIn("CONNECT SPOTIFY again", music_tools.delete_playlist("gym"))


class CallTests(unittest.TestCase):
    def test_a_reply_that_is_not_json_counts_as_done(self):
        # The real queue endpoint answers with plain text, which used to crash call()
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = b"0aBcD-not-json"
        with mock.patch("spotify_connect.token", lambda: "key"), \
                mock.patch("spotify_connect.urllib.request.urlopen", return_value=reply):
            self.assertEqual(spotify_connect.call("POST", "/me/player/queue", uri="x"), {})


class WeakMatchTests(FakeSpotify):
    def song(self, name, artist):
        return {"type": "track", "uri": "spotify:track:" + name, "name": name, "artists": [{"name": artist}]}

    def test_looks_right(self):
        back_in_black = self.song("Back In Black", "AC/DC")
        self.assertTrue(music_tools.looks_right("bck in blak", back_in_black))           # typos are fine
        self.assertTrue(music_tools.looks_right("Back in Black AC/DC", back_in_black))   # artist words count too
        self.assertTrue(music_tools.looks_right("Harder Better Faster Stronger",
                                                self.song("Harder, Better, Faster, Stronger", "Daft Punk")))
        self.assertFalse(music_tools.looks_right("zzqx not a real song", self.song("Sweetness", "Elliot James Reay")))

    def test_make_playlist_leaves_out_a_wrong_looking_match(self):
        self.songs["zzqx"] = self.song("Sweetness", "Elliot James Reay")     # Spotify "finds" gibberish
        reply = music_tools.make_playlist("Rock", ["Get Lucky", "zzqx"])
        self.assertEqual(reply, "Made 'Rock' with 1 songs. Left out, not sure these are right: "
                                "'zzqx' (best guess: Sweetness by Elliot James Reay).")
        self.assertEqual(self.sent[-1][2], {"uris": ["spotify:track:lucky"]})   # Sweetness was NOT added

    def test_add_to_playlist_refuses_a_wrong_looking_match(self):
        self.songs["zzqx"] = self.song("Sweetness", "Elliot James Reay")
        self.assertIn("Didn't add anything", music_tools.add_to_playlist("gym", "zzqx"))
        self.assertEqual(self.sent, [])


class NameMatchTests(unittest.TestCase):
    def test_matching(self):
        names = ["Chill Vibes 🌙", "Gym", "Chill"]
        self.assertEqual(music_tools.best_name_match("CHILL", names), "Chill")         # exact beats "inside"
        self.assertEqual(music_tools.best_name_match("vibes", names), "Chill Vibes 🌙")  # inside the name
        self.assertEqual(music_tools.best_name_match("gim", names), "Gym")             # a typo
        self.assertIsNone(music_tools.best_name_match("road trip", names))             # nothing close

    def test_filler_words_are_ignored(self):                     # the bug Rex's timing test found
        names = ["Gym", "Chill Songs", "My Playlist #1"]
        self.assertEqual(music_tools.best_name_match("gym playlist", names), "Gym")
        self.assertEqual(music_tools.best_name_match("my gym playlist", names), "Gym")
        self.assertEqual(music_tools.best_name_match("the chill playlist", names), "Chill Songs")
        self.assertEqual(music_tools.best_name_match("my playlist #1", names), "My Playlist #1")  # a real name

    def test_says_mine(self):
        self.assertTrue(music_tools.says_mine("My gym playlist"))
        self.assertFalse(music_tools.says_mine("a gym playlist"))
        self.assertFalse(music_tools.says_mine("Mystery Mix"))   # "my" inside a word doesn't count


if __name__ == "__main__":
    unittest.main()
