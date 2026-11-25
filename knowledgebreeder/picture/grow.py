"""kb grows from your cards: the lines on your cards that would make kb itself better, as kb's own to-do list.

Two places feed it. kb's own card (the one named KnowledgeBreeder or kb): what is unfinished on it, the needs still
waiting, its ideas and its open decisions. And every other card: a reusable part or an idea that names kb, such
as "the eight-stage runner with a human gate | KnowledgeBreeder planned to build this same runner". A link that only
says two cards are alike is left out: it is not something to build. No model reads anything here.

You say which to build, which not now, and which are done. kb keeps those marks in work/grow.json, so a line you
answered stays answered when the cards come in again. The build list copies out as one plain text, ready to hand to
whoever builds kb next.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path

from . import engines

_KB = re.compile(r"(?<![\d.,] )\b(kb|knowledge ?breeder)\b", re.IGNORECASE)
STATES = ("build", "later", "done")
# what each kind of line is, in the order they come
KINDS = ("unfinished", "need", "decision", "idea", "part")


def names_kb(text: str) -> bool:
    return bool(_KB.search(text or ""))


def is_kb(card: dict) -> bool:
    """kb's own card: its name or one of its other names is kb or KnowledgeBreeder."""
    return any(_KB.fullmatch(" ".join(str(n).split())) or str(n).lower().startswith("knowledgebreeder")
               for n in [card.get("name") or "", *(card.get("aliases") or [])])


def _id(card_id: str, kind: str, what: str) -> str:
    return hashlib.sha1(f"{card_id}|{kind}|{' '.join(what.split()).lower()}".encode()).hexdigest()[:12]


def _parts(item) -> list[str]:
    return [str(x) for x in item if x] if isinstance(item, list) else [str(item)] if item else []


def lines(cards: dict) -> list[dict]:
    """Every line that would make kb better. Each: id, kind, card, card_id, what, why (why it helps kb, or who it
    waits on)."""
    out: list[dict] = []

    def add(c: dict, kind: str, what: str, why: str = "") -> None:
        what = " ".join(what.split())
        if what:
            out.append({"id": _id(c["id"], kind, what), "kind": kind, "card": c.get("name") or c["id"],
                        "card_id": c["id"], "what": what, "why": " ".join(why.split())})

    for c in cards.values():
        if is_kb(c):
            for item in c.get("unfinished") or []:
                p = _parts(item)
                if p:
                    add(c, "unfinished", p[0], " · ".join(p[1:]))
            for item in c.get("needs") or []:
                p = _parts(item)
                who = p[-1] if len(p) > 2 else ""
                if p and engines.waiting(item) and not engines.YOU.match(who):   # yours wait in Where your work waits
                    add(c, "need", p[0], who)
            for kind, field in (("decision", "decisions"), ("idea", "ideas")):
                for item in c.get(field) or []:
                    p = _parts(item)
                    if p:
                        add(c, kind, p[0], " · ".join(p[1:]))
            continue
        for kind, field in (("idea", "ideas"), ("part", "parts")):
            for item in c.get(field) or []:
                p = _parts(item)
                if p and names_kb(" ".join(p)):
                    add(c, kind, p[0], " · ".join(p[1:]))
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: KINDS.index(x["kind"])):
        if x["id"] not in seen:
            seen.add(x["id"])
            uniq.append(x)
    return uniq


class Marks:
    """Your answers, kept in one small file: build, not now, or done, with the day you said it."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def all(self) -> dict[str, dict]:
        try:
            got = json.loads(self.path.read_text(encoding="utf-8")).get("marks") or {}
        except (OSError, ValueError, AttributeError):
            return {}
        return {k: v for k, v in got.items() if isinstance(v, dict) and v.get("state") in STATES}

    def set(self, item_id: str, state: str, today: date) -> dict:
        if not re.fullmatch(r"[0-9a-f]{12}", item_id or ""):
            raise KeyError("no such line.")
        if state not in (*STATES, ""):
            raise KeyError("state must be build, later, done or empty.")
        marks = self.all()
        if state:
            marks[item_id] = {"state": state, "at": today.isoformat()}
        else:
            marks.pop(item_id, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".part")
        tmp.write_text(json.dumps({"marks": marks}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        return marks


def sort(items: list[dict], marks: dict[str, dict]) -> dict[str, list[dict]]:
    """The lines by your answer: build, new (not answered yet), later, done."""
    out: dict[str, list[dict]] = {"build": [], "new": [], "later": [], "done": []}
    for x in items:
        out[(marks.get(x["id"]) or {}).get("state", "new")].append(x)
    return out


def build_text(items: list[dict], intro: str, from_word: str) -> str:
    """The build list as plain text: one numbered line each, with the card it came from."""
    rows = [intro]
    for i, x in enumerate(items, 1):
        why = f": {x['why']}" if x["why"] else ""
        rows.append(f"{i}. {x['what']} ({from_word} {x['card']}{why})")
    return "\n".join(rows)
