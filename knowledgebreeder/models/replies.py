"""Reading a model's answer. Small local models wrap JSON in words, fences and thinking: this finds it."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
_DECODER = json.JSONDecoder()


def json_from(text: str) -> Any:
    """The first JSON object or list in a text. ValueError when there is none."""
    t = _THINK.sub(" ", text or "")
    for opener, kind in (("{", dict), ("[", list)):         # an object first: "[1]" in a sentence is not the answer
        for i, ch in enumerate(t):
            if ch == opener:
                try:
                    value, _end = _DECODER.raw_decode(t, i)
                except ValueError:
                    continue
                if isinstance(value, kind):
                    return value
    raise ValueError("no JSON in the answer")
