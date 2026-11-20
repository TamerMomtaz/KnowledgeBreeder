"""Models kb may ask, and the gate that decides where your data is allowed to go.

kb works with rules wherever rules are enough. Where a model helps (advice,
reading a saved page against your projects), it asks one of the models you
list in one private file, work/models.json:

    local runtime   anything that speaks the OpenAI chat protocol on your own
                    machine (Ollama, llama.cpp, LM Studio). No key, no internet.
    a key           the Claude API through the official SDK, for the hard
                    questions. Never without your yes for that run.

The gate goes by destination, not by name. A model on this machine is always
allowed. A model on your own network is allowed when its entry says "lan".
Anything else is refused unless you name it with --allow for that one run, and
the refusal says what would have been sent and where. A key is read from your
environment at the moment of the call. It is never written to a file or a log.

    from knowledgebreeder import models
    book = models.load("work/models.json")
    answer = models.ask(book.get("local"), system="...", user="...")
    obj, answer = models.ask_json(book.get("key"), "...", "...", allow={"key"})
"""

from .client import (HERE, NETWORK, OUTSIDE, Answer, ModelError, Refused, allowed, ask, ask_json, gate, offered,
                     place)
from .config import DEFAULT_PATH, Book, Model, example, load
from .replies import json_from

__all__ = ["Answer", "Book", "DEFAULT_PATH", "HERE", "Model", "ModelError", "NETWORK", "OUTSIDE", "Refused",
           "allowed", "ask", "ask_json", "example", "gate", "json_from", "load", "offered", "place"]
