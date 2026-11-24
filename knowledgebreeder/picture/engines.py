"""Where your work waits: two small engines from operations research, run on your cards. No model, no network.

What frees the most (network flows). Every need that is not met waits on someone or something: the "by what" part of
the need. A need counts until the card says it is met. kb groups those needs by who they wait on. A card is free when nothing on it waits any more, so for each
person or thing kb counts the cards that would be free if they did their part. Cards that wait on one thing only are
one step from free; the ones tied to most other cards come first, because they move most.

How long things wait (queues). Little's law: what is open (L) = how fast it closes (λ) × how long it waits (W). L is
counted on the cards now: needs not met, open decisions and unfinished work. λ is read from the versions kb keeps of
your cards: a need that became met, or a need, decision or unfinished piece that left a card, closed; one that came
onto a card opened. kb cannot tell done from dropped, and a reworded item can count as one closed and one opened, so
the pace is a sketch. It and the counts behind it are shown only after two weeks of versions, because in the first
days most of what "opens" is cards being written out in more detail. A queue settles only while things close at least
as fast as they open; when more open than close, the wait has no ceiling.

Both come from the research "Mathematical Engines of Plan→T", carried over to your own work.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from itertools import pairwise

from .cards import by_what, is_unknown, met
from .changes import NOT_KNOWN, diff, versions
from .store import Picture

LOOPS = ("needs", "decisions", "unfinished")
MIN_DAYS = 14                                             # days of versions before kb reads a pace
YOU = re.compile(r"^(tee|me|myself|you|i)\b", re.I)
NOBODY = ("", "unknown", "nothing", "none", "nobody", "n/a", "-")


def who(need: list[str]) -> tuple[str, bool]:
    """Who or what a need waits on, as written on the card without the part in brackets, and whether it is you."""
    raw = re.sub(r"\s*\(.*$", "", by_what(need)).strip().rstrip(".")
    if raw.lower() in NOBODY:
        return "", False
    return raw, bool(YOU.match(raw))


def waiting(need: list[str]) -> bool:
    """A need that is not known to be met: not met, partly met, or not said."""
    return bool(need) and not is_unknown(need[0]) and (len(need) < 2 or met(need[1]) != "yes")


def _open(c: dict) -> dict[str, list[list[str]]]:
    out = {"needs": [n for n in c.get("needs", []) if n and waiting(n)]}
    for k in ("decisions", "unfinished"):
        out[k] = [x for x in c.get(k, []) if x and not is_unknown(x[0])]
    return out


def frees(pic: Picture, top: int = 6) -> dict:
    """Needs that are not met, grouped by who they wait on, and the cards one step from free."""
    deg = pic.degree()
    groups: dict[str, dict] = {}
    on_card: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for cid, c in pic.cards.items():
        for n in c.get("needs", []):
            if not n or not waiting(n):
                continue
            name, you = who(n)
            key = "you" if you else (name.casefold() or "")
            g = groups.setdefault(key, {"who": name, "you": you, "nobody": not name, "needs": 0, "cards": set()})
            g["needs"] += 1
            g["cards"].add(cid)
            on_card[cid].append((key, n))
    rows = []
    for key, g in groups.items():
        free = sorted((cid for cid in g["cards"] if all(k == key for k, _ in on_card[cid])),
                      key=lambda cid: (-deg[cid], pic.name(cid)))
        rows.append({"who": g["who"], "you": g["you"], "nobody": g["nobody"], "needs": g["needs"],
                     "cards": len(g["cards"]), "free": [pic.name(cid) for cid in free]})
    rows.sort(key=lambda r: (-len(r["free"]), -r["cards"], -r["needs"], r["who"].casefold()))
    one = [{"card": pic.name(cid), "need": ns[0][1][0], "who": who(ns[0][1])[0], "you": who(ns[0][1])[1],
            "links": deg[cid]} for cid, ns in on_card.items() if len(ns) == 1]
    one.sort(key=lambda x: (-x["links"], x["card"].casefold()))
    mine = next((r for r in rows if r["you"]), None)
    return {"waiting": sum(len(v) for v in on_card.values()), "cards": len(on_card),
            "you": {"needs": mine["needs"], "cards": mine["cards"], "free": len(mine["free"])} if mine else None,
            "by": rows[:top], "more": max(0, len(rows) - top), "one_step": one[:top], "one_step_all": len(one)}


def _day(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def clock(pic: Picture, today: date | None = None, top: int = 5) -> dict:
    """What is open now, how fast it closes, and which cards have been quiet longest."""
    today = today or date.today()
    now = {k: 0 for k in LOOPS}
    quiet = []
    for cid, c in pic.cards.items():
        o = _open(c)
        n = sum(len(v) for v in o.values())
        for k in LOOPS:
            now[k] += len(o[k])
        last = _day(c.get("last_date")) or _day(c.get("last_activity"))
        if n and last:
            quiet.append({"card": c["name"], "open": n, "days": max(0, (today - last).days)})
    quiet.sort(key=lambda x: (-x["days"], -x["open"], x["card"].casefold()))
    opened = closed = 0
    first = None
    for cid in pic.history:
        if cid not in pic.cards:
            continue
        vs = versions(pic, cid)
        for old, new in pairwise(vs):
            d = _day(old.get("recorded")) if old.get("recorded") not in (None, NOT_KNOWN) else None
            if d and (first is None or d < first):
                first = d
            ch = diff(old, new)
            opened += sum(1 for x in ch["new"] if x["part"] in LOOPS)
            closed += sum(1 for x in ch["gone"] if x["part"] in LOOPS)
            closed += sum(1 for x in ch["met"] if x["now"] == "yes")
    days = (today - first).days if first else 0
    total = sum(now.values())
    pace = wait = None
    if days >= MIN_DAYS:
        pace = closed * 7 / days
        wait = total / pace if pace else None
    return {"open": {**now, "total": total}, "days": days, "since": first.isoformat() if first else None,
            "opened": opened, "closed": closed, "ready": days >= MIN_DAYS, "per_week": pace, "wait_weeks": wait,
            "growing": opened > closed, "quiet": quiet[:top]}


def run(pic: Picture, today: date | None = None) -> dict:
    return {"frees": frees(pic), "clock": clock(pic, today)}


def num(x: float) -> str:
    return f"{x:.1f}" if x < 10 else f"{x:.0f}"


def md(r: dict, lang: str = "en") -> str:
    """The same as the page box, as text for the terminal."""
    from .serve import _t
    f, c = r["frees"], r["clock"]
    def who_is(x: dict, inside: bool = False) -> str:
        if x["you"]:
            return _t(lang, "eng_you_in" if inside else "eng_you_name")
        return x["who"] or _t(lang, "eng_nobody_in" if inside else "eng_nobody")

    L = [f"# {_t(lang, 'eng_h')}", "", _t(lang, "eng_note"), "", f"## {_t(lang, 'eng_frees')}", ""]
    if not f["waiting"]:
        L.append(_t(lang, "eng_no_waiting"))
    else:
        if f["you"]:
            L.append(_t(lang, "eng_you", n=f["you"]["needs"], all=f["waiting"], c=f["you"]["cards"]))
        for g in f["by"]:
            say = "eng_row_free_nobody" if g["nobody"] else "eng_row_free"
            free = " " + _t(lang, say, names=", ".join(g["free"])) if g["free"] else ""
            L.append("- " + _t(lang, "eng_row", who=who_is(g), n=g["needs"], c=g["cards"]) + free)
        if f["more"]:
            L.append("- " + _t(lang, "eng_more", n=f["more"]))
        if f["one_step"]:
            L += ["", _t(lang, "eng_one")]
            L += [f"- {x['card']}: {x['need']} ({_t(lang, 'eng_waits_on', who=who_is(x, True))})" for x in f["one_step"]]
    o = c["open"]
    L += ["", f"## {_t(lang, 'eng_wait')}", "", _t(lang, "eng_open", n=o["needs"], d=o["decisions"], u=o["unfinished"])]
    L.append(pace(c, lang))
    if c["ready"] and (c["opened"] or c["closed"]):
        L.append(_t(lang, "eng_flow", o=c["opened"], c=c["closed"]) + (" " + _t(lang, "eng_growing") if c["growing"] else ""))
    if c["quiet"]:
        L += ["", f"## {_t(lang, 'eng_quiet')}", ""]
        L += [f"- {x['card']}. " + _t(lang, "eng_quiet_row", n=x["open"], d=x["days"]) for x in c["quiet"]]
    return "\n".join(L) + "\n"


def pace(c: dict, lang: str = "en") -> str:
    """One sentence on the pace: how long a new loop waits, or why kb cannot say yet."""
    from .serve import _t
    if c["ready"] and c["per_week"]:
        return _t(lang, "eng_pace", p=num(c["per_week"]), w=num(c["wait_weeks"]))
    if c["ready"]:
        return _t(lang, "eng_none_closed", d=c["days"])
    return _t(lang, "eng_early", d=c["days"], m=MIN_DAYS)
