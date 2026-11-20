"""The scout: reads what you saved against your projects, so a chance is not missed for lack of reading.

You save pages into a folder: a call for proposals, a newsletter, an
announcement, a post. For each one the scout

    1. finds the cards it shares words with (rules, no model)
    2. asks a model one question: is there a real chance here for one of these
       projects, and which words of the text show it
    3. checks the answer against the text: the quote must be in it, word for
       word, and so must the words that give the deadline. A project the model
       names must be one kb offered.
    4. writes one line in a ledger, whatever the verdict

The ledger is the point. It holds every source the scout has read, including
the ones it passed over and why, so you can see what it said no to. Nothing can
promise that no chance is ever missed. A scout that shows its misses can be
checked, and corrected.

It reads what you give it. It does not search the web. A saved page is someone
else's text: the model is told to treat it as data, and kb believes nothing the
model says about it that the text does not show.
"""

from .scout import (Ledger, check, excerpt, match, open_now, prompt, read_source, scout_md, log_md, sources, verdicts,
                    watch)

__all__ = ["Ledger", "check", "excerpt", "log_md", "match", "open_now", "prompt", "read_source", "scout_md",
           "sources", "verdicts", "watch"]
