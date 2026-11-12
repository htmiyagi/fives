"""
brain.py - connects the language model (Lesson 1) to the tools (Lesson 2).

The whole trick is one loop:
  1. send the conversation to the model
  2. if it asks for tools, run them and add the results to the conversation
  3. repeat until it answers in plain words
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
    "pause": "pause", "stop": "pause",
    "resume": "resume", "play": "resume", "unpause": "resume",
    "back": "previous", "previous": "previous", "previous song": "previous", "go back": "previous",
    "restart": "restart",
}
POLITE_WORDS = {"please", "rex", "hey"}   # dropped before matching, so "skip please" counts as "skip"


def shortcut_action(user_text: str) -> str | None:
    """'Skip!' -> 'skip'. Returns None for anything that isn't a plain one-word-ish command."""
    no_punctuation = user_text.lower().translate(str.maketrans("", "", string.punctuation))
    words = [word for word in no_punctuation.split() if word not in POLITE_WORDS]
    return SHORTCUTS.get(" ".join(words))


def new_conversation() -> list:
    """Start a fresh conversation: FIVES's personality, plus facts the model can't see (your playlist names).
    Read once per conversation (~0.25s), not every message, so replies stay fast."""
    facts = [note for note in (playlist_note(),) if note]
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


def think(messages: list, user_text: str, on_tool=None) -> str:
    """Handle one request. Adds everything to `messages` and returns the reply."""
    messages.append({"role": "user", "content": user_text})

    action = shortcut_action(user_text)
    if action:                             # a plain "skip" etc: no model needed
        result = run_tool("music_controls", {"action": action})
        if on_tool:
            on_tool("music_controls", {"action": action}, result)
        messages.append({"role": "assistant", "content": result})   # so Rex remembers what happened
        return result

    for _ in range(config.MAX_TOOL_ROUNDS):
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

        for call in calls:                 # run every tool it asked for
            name = call.function.name
            args = call.function.arguments or {}
            result = run_tool(name, args)
            if on_tool:
                on_tool(name, args, result)
            messages.append({"role": "tool", "tool_name": name, "content": result})

    return "I hit my limit of tool calls for one request, so I stopped."
