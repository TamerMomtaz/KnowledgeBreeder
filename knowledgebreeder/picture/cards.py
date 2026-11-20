"""Reading PROJECT CARDs: plain text in, plain dicts out.

A card is what one project, chat or notebook says about itself, under fixed
headings (the inventory prompt in the README produces them). Cards arrive
written two ways, and both are read:

    WHAT IT NEEDS                               WHAT IT NEEDS: flour | met? no | by what: nothing
    - flour | met? no | by what: nothing

"unknown" is kept as a fact about the card, never filled in.
"""

from __future__ import annotations

import re
from datetime import date

HEADER = ("name", "one_line", "area", "kind", "last_activity", "source", "aliases")
SECTIONS = ("PURPOSE", "WHAT EXISTS", "WHAT IT CAN DO", "WHAT IT NEEDS", "UNFINISHED", "IDEAS NOT STARTED",
            "REUSABLE PARTS", "LINKS TO MY OTHER WORK", "RECURRING THEMES", "OPEN DECISIONS",
            "WHAT YOU COULD NOT SEE")
KEYS = {"PURPOSE": "purpose", "WHAT EXISTS": "exists", "WHAT IT CAN DO": "can_do", "WHAT IT NEEDS": "needs",
        "UNFINISHED": "unfinished", "IDEAS NOT STARTED": "ideas", "REUSABLE PARTS": "parts",
        "LINKS TO MY OTHER WORK": "links", "RECURRING THEMES": "themes", "OPEN DECISIONS": "decisions",
        "WHAT YOU COULD NOT SEE": "unseen"}
LISTS = tuple(k for k in KEYS.values() if k != "purpose")
PURPOSE_KEYS = ("problem", "who_it_serves", "my_goal")

_START = re.compile(r"^\s*(?:#{1,6}\s*)?PROJECT CARD\s*[\d.:#-]*\s*$")
_END = re.compile(r"^\s*(?:#{1,6}\s+\S|-{3,}\s*$|`{3})")
_HEAD = re.compile(r"^\s*(%s)\s*:\s*(.*)$" % "|".join(HEADER), re.I)
_SECTION = re.compile(r"^[\s#*]*(%s)\b\**\s*(?:\([^)]*\))?\s*(?::\s*(.*))?$" % "|".join(SECTIONS))
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_HINT = re.compile(r"^\(.*\)$")


def slug(name: str) -> str:
    return re.sub(r"[\W_]+", "-", name.lower(), flags=re.UNICODE).strip("-") or "card"


def fields(text: str) -> list[str]:
    return [f.strip() for f in re.split(r"\s*\|\s*", text.strip()) if f.strip()]


def is_unknown(text: str) -> bool:
    return text.strip().lower().rstrip(".") in ("unknown", "none known", "")


def latest_date(text: str) -> str | None:
    found = []
    for m in _DATE.findall(text or ""):
        try:
            found.append(date.fromisoformat(m))
        except ValueError:
            pass
    return max(found).isoformat() if found else None


def met(text: str) -> str:
    """How far a need is met: yes, partly, no or unknown."""
    t = re.sub(r"^(is it )?met( today)?\??\s*", "", text.strip().lower())
    if t.startswith("yes"):
        return "yes"
    if t.startswith("part"):
        return "partly"
    if re.match(r"(no|not)\b", t):
        return "no"
    return "unknown"


def by_what(need: list[str]) -> str:
    """The third field of a need, without the form's own words in front of it."""
    return re.sub(r"^by what\??:?\s*", "", " | ".join(need[2:]).strip(), flags=re.I)


def _split_outside_quotes(text: str, sep: str = ";") -> list[str]:
    out, buf, inside = [], [], False
    for ch in text:
        if ch in '"\u201c\u201d':
            inside = (ch == "\u201c") or (ch == '"' and not inside)
        if ch == sep and not inside:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [p.strip() for p in out if p.strip()]


def _inline_items(text: str) -> list[str]:
    """Split 'a | how; b | how' into items, without cutting a sentence that merely holds a semicolon."""
    pieces = _split_outside_quotes(text)
    if all("|" in p for p in pieces) or not any("|" in p for p in pieces):
        return pieces
    out: list[str] = []
    for p in pieces:
        if "|" in p or not out:
            out.append(p)
        else:
            out[-1] += "; " + p
    return out


def _new(origin: str) -> dict:
    card = {h: "" for h in HEADER if h != "aliases"}
    card.update({"aliases": [], "purpose": {}, "unknown": [], "notes": [], "origin": origin})
    card.update({k: [] for k in LISTS})
    return card


def _add_item(card: dict, key: str, text: str) -> None:
    text = text.strip()
    if not text or _HINT.match(text):
        return
    if key == "purpose":
        for part in fields(text):
            k, sep, v = part.partition(":")
            k = k.strip().lower()
            if sep and k in PURPOSE_KEYS:
                if is_unknown(v) or v.strip().lower().startswith("unknown"):
                    card["unknown"].append(k)
                if v.strip():
                    card["purpose"][k] = v.strip()
            elif part:
                card["purpose"]["other"] = (card["purpose"].get("other", "") + " " + part).strip()
        return
    f = fields(text)
    if not f:
        return
    if is_unknown(f[0]) and len(f) == 1:
        card["unknown"].append(key)
        return
    if f[0].lower().startswith("unknown"):
        card["unknown"].append(key)
    card[key].append(f)


def _finish(card: dict) -> dict | None:
    if not card["name"]:
        return None
    card["id"] = slug(card["name"])
    card["last_date"] = latest_date(card["last_activity"])
    card["unknown"] = sorted(set(card["unknown"]))
    for k in PURPOSE_KEYS:
        if k not in card["purpose"] and k not in card["unknown"]:
            card["unknown"].append(k)
    card["unknown"].sort()
    return card


def parse(text: str, origin: str = "") -> list[dict]:
    """Every PROJECT CARD in a text, in order. Text outside cards is ignored."""
    cards: list[dict] = []
    card: dict | None = None
    key: str | None = None
    blank = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if _START.match(line):
            if card and (done := _finish(card)):
                cards.append(done)
            card, key, blank = _new(origin), None, False
            continue
        if card is None:
            continue
        sec = _SECTION.match(line)
        if sec:
            key, blank = KEYS[sec.group(1)], False
            rest = (sec.group(2) or "").strip()
            if rest:
                for item in ([rest] if key == "purpose" else _inline_items(rest)):
                    _add_item(card, key, item)
            continue
        if _END.match(line):
            if done := _finish(card):
                cards.append(done)
            card, key = None, None
            continue
        if not line.strip():
            blank = True
            continue
        head = _HEAD.match(line) if key is None else None
        if head:
            h, v = head.group(1).lower(), head.group(2).strip()
            if _HINT.match(v):
                v = ""
            if h == "aliases":
                card["aliases"] = [x.strip() for x in re.split(r"[;,]", v) if x.strip()]
            else:
                card[h] = v
            continue
        bullet = _BULLET.match(line)
        if key is None:
            card["notes"].append(line.strip())
        elif bullet:
            _add_item(card, key, bullet.group(1))
        elif key == "purpose" and line.partition(":")[0].strip().lower() in PURPOSE_KEYS:
            _add_item(card, key, line)
        elif blank:
            card["notes"].append(line.strip())      # a loose paragraph after the card's last list
        elif card[key]:
            card[key][-1][-1] += " " + line.strip()  # a wrapped line continues the item above it
        else:
            _add_item(card, key, line)
        blank = False
    if card and (done := _finish(card)):
        cards.append(done)
    return cards


def parse_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return parse(f.read(), origin=str(path))
