"""kb's crew: what comes in is routed to the agent that owns that kind of thing.

The inlet is the inbox (and the page's own boxes). The router reads each thing once and hands it to every agent that
claims it, by plain rules you can read here, never by a model's guess. An agent does one job and leaves its work where
the rest of kb reads it (Your ideas, the picture, the chances). Each agent is listed with what it takes and what it
gives, so the page and the explainer can say who did what.

Agents now:

    frame-outer   takes book titles. Gives each book's framework, a platform of its own, features for the platforms
                  on your cards, and a song to remember it by (picture/books.py).

The inbox's own readers (links, PDFs, Word files) and the scout stay where they are; they become agents of the crew
as they move here. A line the router does not claim stays in the inbox, read as before.
"""

from __future__ import annotations

import re

AGENTS = {
    "frame-outer": {"takes": "book titles", "file": "picture/books.py",
                    "gives": "framework, a platform of its own, features for your platforms, a song"},
}

# "book: Algorithms to Live By", "Book - Deep Work, Cal Newport", "كتاب: فن الحرب", "📖 Range"
_BOOK = re.compile(r"^\s*(?:[-*•]\s*)?(?:(?:books?|كتاب|كتب)\s*[:：\-–—]|📖|📚)\s*(.+?)\s*$", re.IGNORECASE)
_HEAD = re.compile(r"^\s*(?:books?|كتب|الكتب)\s*[:：]?\s*$", re.IGNORECASE)
_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s*(.+?)\s*$")


def books_in(text: str) -> list[str]:
    """Book titles in a text: each line that starts with book: (or كتاب:, or a book emoji), and the list under a line
    that says only Books. A title is kept as written, each once."""
    out: list[str] = []
    under = False
    for line in (text or "").splitlines():
        if _HEAD.match(line):
            under = True
            continue
        m = _BOOK.match(line)
        title = m.group(1) if m else None
        if title is None and under:
            item = _ITEM.match(line)
            if item:
                title = item.group(1)
            elif line.strip():
                title = line.strip()
            else:
                under = False
        if title:
            title = " ".join(title.split()).strip(" .،")[:200]
            if title and title.lower() not in (x.lower() for x in out):
                out.append(title)
    return out


def route(text: str) -> dict[str, list[str]]:
    """{agent: what it takes from this text}. Empty when no agent claims anything in it."""
    out: dict[str, list[str]] = {}
    if books := books_in(text):
        out["frame-outer"] = books
    return out
