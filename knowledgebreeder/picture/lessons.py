"""Lessons: the person's own standing rules for advice, in their own words, followed by every advice run.

One lesson per line in a private Markdown file (work/lessons.md by default, never committed). A line that starts
with "#" is a heading or a note to self and is skipped, and so is a blank line. A leading "- " and a date in
brackets are optional, so the file can be written by hand or grown with ``kb picture lesson "..."``.

kb cannot check that a model followed a lesson. The person's rating of each run is that check.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

ROOM = 4_000            # characters of lessons sent with each run; the newest are kept when there are more

HEAD = ("# Lessons for kb's advice\n\n"
        "# One lesson per line, in your own words. Every advice run follows them. Edit or delete lines freely.\n\n")

_BULLET = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_DATED = re.compile(r"^\[\d{4}-\d{2}-\d{2}\]\s*")


def read(path: str | Path) -> list[str]:
    """The lessons in the file, in its order. No file means no lessons."""
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "<!--")):
            continue
        s = " ".join(_DATED.sub("", _BULLET.sub("", s)).split())
        if s:
            out.append(s)
    return out


def fit(lessons: list[str], room: int = ROOM) -> tuple[list[str], int]:
    """The newest lessons that fit in ``room`` characters, in file order, and how many older ones did not."""
    kept, used = [], 0
    for s in reversed(lessons):
        if used + len(s) + 6 > room:
            break
        kept.append(s)
        used += len(s) + 6
    kept.reverse()
    return kept, len(lessons) - len(kept)


def add(path: str | Path, text: str, today: date) -> tuple[list[str], bool]:
    """Append one dated lesson. Returns every lesson now in the file, and whether this one was new."""
    text = " ".join(text.split())
    if not text:
        raise KeyError("a lesson needs words, for example: kb picture lesson \"Quiet is not dead.\"")
    have = read(path)
    if text.casefold() in {s.casefold() for s in have}:
        return have, False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    before = p.read_text(encoding="utf-8") if p.is_file() else ""
    with p.open("a", encoding="utf-8") as f:
        if not before:
            f.write(HEAD)
        elif not before.endswith("\n"):
            f.write("\n")
        f.write(f"- [{today.isoformat()}] {text}\n")
    return read(path), True


def numbered(lessons: list[str]) -> str:
    return "\n".join(f"L{i} {s}" for i, s in enumerate(lessons, 1))
