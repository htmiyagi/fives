"""
brain.py - connects the language model (Lesson 1) to the tools (Lesson 2).

The whole trick is one loop:
  1. send the conversation to the model
  2. if it asks for tools, run them and show the tools' own sentences as the reply ("run-first")
  3. only go another round if a tool failed or there may be a step 2 ("...and open Safari")
"""

import string

import ollama

import config
from music_tools import playlist_note
from tools import TOOLS

# Look tools up by name: {"open_app": open_app, ...}
TOOLS_BY_NAME = {fn.__name__: fn for fn in TOOLS}

# Shortcuts: if your WHOLE message is one of these, we run music_controls ourselves, skipping the model.
# Instant, can't be misunderstood, and works even when Ollama is off.
SHORTCUTS = {
    "skip": "skip", "next": "skip", "next song": "skip", "skip song": "skip", "skip this": "skip",
    "skip it": "skip", "skip this song": "skip", "next one": "skip",
    "pause": "pause", "stop": "pause", "pause it": "pause", "pause the music": "pause",
    "resume": "resume", "play": "resume", "unpause": "resume", "keep playing": "resume",
    "back": "previous", "previous": "previous", "previous song": "previous", "go back": "previous",
    "last song": "previous",
    "restart": "restart", "rewind": "restart", "rewind to start": "restart", "start over": "restart",
    "from the top": "restart", "restart song": "restart", "restart the song": "restart",
}
POLITE_WORDS = {"please", "rex", "hey"}   # dropped before matching, so "skip please" counts as "skip"

# Run-first: every tool already answers in a finished sentence ("Playing X by Y."), so we show it as-is.
# Letting the model reword it is how song and artist names got swapped in testing. Also saves a model call.
# Told to the model so a two-part request ("play X and open Safari") comes back as two tool calls in one go.
ONE_GO_RULE = "If a request needs more than one tool, call all of them at once, in the same reply."

# Safety net in case it doesn't: a joining word means there may be a step 2 still to do.
STEP_WORDS = {"and", "then", "also", "plus", "after"}

# How the tools' sentences start when something went wrong (see tools.py and music_tools.py).
FAILED_STARTS = ("Couldn't", "Didn't", "No playlist", "Nothing", "Something", "Spotify said no",
                 "Spotify forgot", "Spotify isn't", "Shortcut failed", "The tool", "There is no tool", "I can ")


def shortcut_action(user_text: str) -> str | None:
    """'Skip!' -> 'skip'. Returns None for anything that isn't a plain one-word-ish command."""
    no_punctuation = user_text.lower().translate(str.maketrans("", "", string.punctuation))
    words = [word for word in no_punctuation.split()
             if word not in POLITE_WORDS and len(word) > 1]   # 1 letter = leftover of a smiley like :D or :P
    return SHORTCUTS.get(" ".join(words))


def sounds_failed(result: str) -> bool:
    """'Couldn't find a song called...' -> True. The model gets a turn to retry or explain."""
    return result.startswith(FAILED_STARTS)


def needs_another_round(user_text: str, results: list[str], first_round: bool) -> bool:
    """Run-first: stop as soon as the tools are done, unless one failed, or the first round ran
    just one tool but you asked for more ('play Halo AND open Notes'). Costs ~0.6s when it fires."""
    if any(sounds_failed(result) for result in results):
        return True
    words = user_text.lower().translate(str.maketrans("", "", string.punctuation)).split()
    return first_round and len(results) == 1 and any(word in STEP_WORDS for word in words)


def new_conversation() -> list:
    """Start a fresh conversation: FIVES's personality, plus facts the model can't see (your playlist names).
    Read once per conversation (~0.25s), not every message, so replies stay fast."""
    facts = [note for note in (ONE_GO_RULE, playlist_note()) if note]
    return [{"role": "system", "content": "\n\n".join([config.PERSONALITY, *facts])}]


def run_tool(name: str, args: dict) -> str:
    """Run one tool the model asked for, and never crash FIVES doing it."""
    fn = TOOLS_BY_NAME.get(name)
    if fn is None:
        return f"There is no tool called {name}."
    try:
        return str(fn(**args))
    except Exception as error:
        return f"The tool {name} failed: {error}"


def run_shortcut(messages: list, action: str, on_tool=None) -> str:
    """Run music_controls ourselves, then write it into the history the same way a real turn looks:
    the model calls the tool -> the tool answers -> the model replies. If we only saved the reply, the model
    would learn "just say 'Skipped!', no tool needed" and start faking it (it really did, in testing)."""
    args = {"action": action}
    result = run_tool("music_controls", args)
    if on_tool:
        on_tool("music_controls", args, result)
    messages.append({"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "music_controls", "arguments": args}}]})
    messages.append({"role": "tool", "tool_name": "music_controls", "content": result})
    messages.append({"role": "assistant", "content": result})
    return result


def think(messages: list, user_text: str, on_tool=None) -> str:
    """Handle one request. Adds everything to `messages` and returns the reply."""
    messages.append({"role": "user", "content": user_text})

    action = shortcut_action(user_text)
    if action:                             # a plain "skip" etc: no model needed
        return run_shortcut(messages, action, on_tool)

    said_before = []                       # tool sentences from earlier rounds, so a step 2 doesn't hide step 1
    for round_number in range(config.MAX_TOOL_ROUNDS):
        response = ollama.chat(
            model=config.MODEL,
            messages=messages,
            tools=TOOLS,
            think=config.THINK,
            options={"num_ctx": config.CONTEXT_TOKENS, "temperature": config.TEMPERATURE},
            keep_alive=config.KEEP_ALIVE,
        )
        messages.append(response.message)

        calls = response.message.tool_calls
        if not calls:                      # plain answer -> we're done
            return response.message.content

        results = []
        for call in calls:                 # run every tool it asked for
            name = call.function.name
            args = call.function.arguments or {}
            result = run_tool(name, args)
            if on_tool:
                on_tool(name, args, result)
            messages.append({"role": "tool", "tool_name": name, "content": result})
            results.append(result)

        if not needs_another_round(user_text, results, first_round=round_number == 0):
            reply = " ".join(said_before + results)   # the tools' own words, names exactly right
            messages.append({"role": "assistant", "content": reply})
            return reply
        said_before = said_before + results   # going another round: keep what's been done so far

    return "I hit my limit of tool calls for one request, so I stopped."
