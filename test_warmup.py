"""
Tests for warmup.py, with no real Ollama: urlopen is swapped for a fake.

Run them:   .venv/bin/python -m unittest test_warmup -v
"""

import json
import unittest
import urllib.error
from unittest import mock

import warmup


class WarmUp(unittest.TestCase):
    def test_asks_ollama_to_load_the_model_without_a_prompt(self):
        with mock.patch("warmup.urllib.request.urlopen") as urlopen:
            reply = warmup.warm_up("qwen3.6:35b", "2h", 16384)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/generate")
        self.assertEqual(json.loads(request.data), {"model": "qwen3.6:35b", "keep_alive": "2h",
                                                     "options": {"num_ctx": 16384}})   # no prompt = just load
        self.assertEqual(reply, "qwen3.6:35b is warmed up.")

    def test_ollama_being_off_is_not_a_crash(self):   # FIVES has to work without Ollama
        with mock.patch("warmup.urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            reply = warmup.warm_up("qwen3.6:35b", "2h", 16384)
        self.assertIn("Couldn't warm up qwen3.6:35b", reply)


if __name__ == "__main__":
    unittest.main()
