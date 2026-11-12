"""
warmup.py - load Rex's model into memory in the background, so your first request isn't slow.

The model is ~22 GB, and loading it from disk takes ~12 seconds. Ollama keeps it loaded for a while
after (config.KEEP_ALIVE), so warming it up when FIVES starts means Rex answers fast right away.
Only uses urllib (Python's built-in web requests), so hub.py doesn't have to load the whole brain.
"""

import json
import threading
import urllib.request

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
LOAD_TIMEOUT_SECONDS = 120   # loading a big model from disk can take a while on a slower Mac


def warm_up(model: str, keep_alive: str, context_tokens: int) -> str:
    """Ask Ollama to load the model. No prompt = "just load it, don't write anything".
    context_tokens must match what brain.py asks for, or the first real request reloads it (2.3s vs 0.2s, tested).
    Never raises: FIVES has to work without Ollama, so a failure comes back as a sentence."""
    body = json.dumps({"model": model, "keep_alive": keep_alive, "options": {"num_ctx": context_tokens}}).encode()
    request = urllib.request.Request(OLLAMA_GENERATE_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=LOAD_TIMEOUT_SECONDS) as reply:
            reply.read()
        return f"{model} is warmed up."
    except Exception as error:
        return f"Couldn't warm up {model}: {error}"


def warm_up_in_background(model: str, keep_alive: str, context_tokens: int) -> None:
    """Start warm_up on its own thread (a second line of work), so nothing waits the ~12s for it."""
    threading.Thread(target=warm_up, args=(model, keep_alive, context_tokens), daemon=True).start()
