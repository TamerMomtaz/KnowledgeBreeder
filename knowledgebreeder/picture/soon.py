"""Coming up: the dates written on your cards and the deadlines of open chances, nearest first.

No model reads anything here. A date counts when it is written as 2026-11-28, 28 November 2026 or November 28, 2026.
A date ahead is shown when it is close. A date that has passed is shown only while the thing it belongs to is still
open and the words just before it say it was a deadline ("due", "before", "closes", "ending" ...), so kb can say
plainly that something slipped instead of staying quiet about it.
"""

from __future__ import annotations

import re
from datetime import date

from . import engines

AHEAD = 45          # days ahead worth showing
BEHIND = 60         # days back a missed deadline is still worth naming

_MONTHS = {m: i for i, ms in enumerate((
    ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
    ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
    ("december", "dec")), start=1) for m in ms}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(20\d\d)\b", re.IGNORECASE)
_MDY = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.IGNORECASE)
_CUE = re.compile(r"\b(due|deadline|before|by|until|till|closes?|closing|ends?|ending|expires?|expiring|submit\w*|"
                  r"no later than|last day)\b", re.IGNORECASE)
# where a date is worth looking for, and whether what it sits on can still be open
_FIELDS = (("one_line", False), ("needs", True), ("unfinished", True), ("decisions", True))


def dates_in(text: str) -> list[tuple[date, int]]:
    """Every date written in the text, with where it starts. Impossible dates (31 February) are skipped."""
    out = []
    for m in _ISO.finditer(text):
        out.append((m.start(), int(m[1]), int(m[2]), int(m[3])))
    for m in _DMY.finditer(text):
        out.append((m.start(), int(m[3]), _MONTHS[m[2].lower()], int(m[1])))
    for m in _MDY.finditer(text):
        out.append((m.start(), int(m[3]), _MONTHS[m[1].lower()], int(m[2])))
    found = []
    for at, y, mo, d in sorted(out):
        try:
            found.append((date(y, mo, d), at))
        except ValueError:
            continue
    return found


def _cued(text: str, at: int) -> bool:
    """Whether the few words just before a date say it is a deadline."""
    return bool(_CUE.search(text[max(0, at - 32):at]))


def _items(card: dict):
    """(field, the item's own words, the full text to search, whether it is still open) for each place a date may be."""
    for field, can_open in _FIELDS:
        v = card.get(field)
        if not v:
            continue
        if isinstance(v, str):
            yield field, v, v, False
            continue
        for item in v:
            parts = [str(x) for x in item if x] if isinstance(item, list) else [str(item)]
            if not parts:
                continue
            still = can_open and (engines.waiting(item) if field == "needs" else True)
            yield field, parts[0], " | ".join(parts), still


def coming(cards: dict, today: date, chances: list[dict] | None = None,
           ahead: int = AHEAD, behind: int = BEHIND) -> list[dict]:
    """What is coming up and what slipped, nearest first. Each: when, days (below 0 = passed), card, what, kind
    (deadline, date, missed or chance), and whose it is when the card says."""
    seen: dict[tuple[str, str], dict] = {}
    rank = {"unfinished": 0, "needs": 1, "decisions": 2, "one_line": 3}
    for cid, c in cards.items():
        for field, what, text, still in _items(c):
            for d, at in dates_in(text):
                days = (d - today).days
                cue = _cued(text, at)
                if 0 <= days <= ahead:
                    kind = "deadline" if cue or field == "unfinished" else "date"
                elif -behind <= days < 0 and still and cue:
                    kind = "missed"
                else:
                    continue
                who = ""
                if field in ("needs", "unfinished"):
                    raw = c.get(field)
                    item = next((x for x in raw if isinstance(x, list) and x and str(x[0]) == what), None)
                    if item and len(item) > 2:
                        who = re.sub(r"\s*\(.*$", "", str(item[-1])).strip()
                row = {"when": d.isoformat(), "days": days, "card": c.get("name") or cid, "id": cid, "kind": kind,
                       "what": _short(what if field != "one_line" else _around(text, at)), "field": field,
                       "who": who}
                key = (cid, row["when"])
                old = seen.get(key)
                if old is None or rank[field] < rank[old["field"]]:
                    seen[key] = row
    rows = list(seen.values())
    for r in chances or []:
        if not r.get("deadline"):
            continue
        days = (date.fromisoformat(r["deadline"]) - today).days
        if 0 <= days <= ahead:
            rows.append({"when": r["deadline"], "days": days, "card": "", "id": "", "kind": "chance", "field": "chance",
                         "what": r.get("what") or r.get("title") or r.get("source") or "", "who": ""})
    rows.sort(key=lambda x: (x["kind"] != "missed", x["days"] if x["kind"] != "missed" else -x["days"], x["card"]))
    return rows


def _around(text: str, at: int, width: int = 90) -> str:
    """The clause of a long line that holds the date, cut at commas or colons, for one-line descriptions."""
    start = max(text.rfind(c, 0, at) for c in (":", ";", ". ")) + 1
    ends = [i for i in (text.find(c, at) for c in (",", ";", ". ")) if i > 0]
    end = min(ends) if ends else len(text)
    s = text[start:end].strip(" ,;:")
    return s if len(s) <= width else s[:width].rsplit(" ", 1)[0] + "…"


def _short(s: str, width: int = 150) -> str:
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width].rsplit(" ", 1)[0] + "…"


def when_words(days: int, lang: str = "en") -> str:
    """'today', 'tomorrow', 'in 3 days', '25 days ago', in English or Arabic."""
    if lang == "ar":
        if days == 0:
            return "اليوم"
        if days == 1:
            return "غدًا"
        if days > 1:
            return f"بعد {days} أيام" if days <= 10 else f"بعد {days} يومًا"
        return f"منذ {-days} أيام" if -days <= 10 else f"منذ {-days} يومًا"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days" if days > 0 else ("yesterday" if days == -1 else f"{-days} days ago")
