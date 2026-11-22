"""Is your picture ready for a model? Five questions asked of every card, and a test of whether it matters.

"AI is only as useful as the foundation it stands on" is a claim. This module asks the questions a data-ready check
asks, of your own cards, and then lets your own ticks test the claim:

    1 current      does the card say when the project was last worked on?
    2 complete     how much of the card is filled in, not "unknown" or missing?
    3 provenance   does it say where its facts come from, and is that more than memory?
    4 one name     is a project under two names, or a name that could be several cards?
    5 owner        does the card name who keeps its facts true? (owner: in the card's header, optional)

A card with no gap is ready, with one gap thin, with two or more (or under a quarter filled in) weak. Ownership
is counted, not held against a card, because most cards are yours.

Every advice run records which cards were weak at the time and marks each evidence line that rests only on weak
cards; the model is not told. The check then reads your ticks: of the pieces that rest only on weak cards, how
many would you act on, against the rest? If weak cards give advice you act on less, the claim holds for you.
"""

from __future__ import annotations

import re
from datetime import date
from statistics import median

from .cards import PURPOSE_KEYS, is_unknown
from .store import Picture, words

PARTS = (*PURPOSE_KEYS, "exists", "can_do", "needs", "unfinished", "ideas", "parts", "links", "themes", "decisions")
THIN, WEAK = 0.40, 0.25            # filled-in share under which a card is thin on content, and weak on its own
MEMORY = ("memory", "my head", "from memory", "ذاكرة", "ذاكرتي")
MIN_PIECES = 5                     # rated pieces each side needs before kb compares them


def filled(c: dict) -> int:
    """How many of the card's twelve parts say something."""
    n = 0
    for k in PARTS:
        if k in c["unknown"]:
            continue
        if k in PURPOSE_KEYS:
            v = c["purpose"].get(k, "")
            n += bool(v) and not is_unknown(v) and not v.strip().lower().startswith("unknown")
        else:
            n += bool(c.get(k))
    return n


def _source(c: dict) -> str:
    s = (c.get("source") or "").strip()
    if not s or is_unknown(s):
        return "none"
    low = s.lower()
    rest = low
    for w in MEMORY:
        rest = rest.replace(w, " ")
    if rest.strip(" ,;.and") == "" and any(w in low for w in MEMORY):
        return "memory"
    return "named"


def same_names(pic: Picture) -> list[tuple[str, str, str]]:
    """Pairs of cards that may be one project under two names: (id, id, why)."""
    out = []
    ids = list(pic.cards)
    toks = {cid: set(words(pic.cards[cid]["name"])) for cid in ids}
    alias = {cid: {a.strip().lower() for a in pic.cards[cid].get("aliases", []) if a.strip()} for cid in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            na, nb = pic.cards[a]["name"].strip().lower(), pic.cards[b]["name"].strip().lower()
            ta, tb = toks[a], toks[b]
            if na in alias[b] or nb in alias[a] or alias[a] & alias[b]:
                out.append((a, b, "a name of one is an alias of the other"))
            elif ta and tb and (ta <= tb or tb <= ta):
                out.append((a, b, "one name holds the other"))
            elif ta and tb and len(ta & tb) / len(ta | tb) >= 0.6:
                out.append((a, b, "the names share most of their words"))
    return out


def _one(word: str) -> str:
    w = word.lower()
    return w[:-3] + "y" if w.endswith("ies") else w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def areas(pic: Picture) -> list[list[str]]:
    """Area names written more than one way: Bakery, bakery, Bakeries."""
    by: dict[tuple, list[str]] = {}
    for a in pic.all_areas():
        by.setdefault(tuple(_one(w) for w in re.findall(r"\w+", a)), []).append(a)
    return [sorted(v) for v in by.values() if len(v) > 1]


def cards(pic: Picture) -> dict[str, dict]:
    """Each card's readiness: its level, its gaps in plain words, and the numbers behind them."""
    twins: dict[str, list[str]] = {}
    for a, b, _why in same_names(pic):
        twins.setdefault(a, []).append(pic.name(b))
        twins.setdefault(b, []).append(pic.name(a))
    out = {}
    for cid, c in pic.cards.items():
        k, src, gaps = filled(c), _source(c), []
        if not c.get("last_date"):
            gaps.append("it does not say when it was last worked on")
        if k / len(PARTS) < THIN:
            gaps.append(f"{k} of {len(PARTS)} parts filled in")
        if src == "none":
            gaps.append("it does not say where its facts come from")
        elif src == "memory":
            gaps.append("its facts come from memory only")
        if cid in twins:
            gaps.append(f"it may be the same project as {', '.join(twins[cid])}")
        level = "weak" if len(gaps) >= 2 or k / len(PARTS) < WEAK else "thin" if gaps else "ready"
        owner = (c.get("owner") or "").strip()
        out[cid] = {"name": c["name"], "level": level, "gaps": gaps, "filled": k, "parts": len(PARTS),
                    "source": src, "owner": "" if is_unknown(owner) else owner}
    return out


def weak(pic: Picture) -> set[str]:
    return {cid for cid, r in cards(pic).items() if r["level"] == "weak"}


def ticks(runs: list[dict]) -> dict:
    """Your ticks split by whether a piece rests only on weak cards. ``runs`` are page.gather results; only runs
    that recorded the cards' readiness count, and only answers you rated."""
    on, rest, counted = [0, 0], [0, 0], 0
    for d in runs:
        if not d.get("readiness"):
            continue
        counted += 1
        for a in d["answers"]:
            if a.get("error") or a.get("rated") is None:
                continue
            for p in a["pieces"]:
                side = on if p["lines"] and all(ln.get("weak") for ln in p["lines"]) else rest
                side[0] += p["n"] in a["rated"]
                side[1] += 1
    enough = on[1] >= MIN_PIECES and rest[1] >= MIN_PIECES
    return {"runs": counted, "weak": {"acted": on[0], "pieces": on[1]}, "rest": {"acted": rest[0], "pieces": rest[1]},
            "enough": enough}


def check(pic: Picture, runs: list[dict] | None = None, today: date | None = None) -> dict:
    r = cards(pic)
    n = len(r)
    when = [x["name"] for cid, x in r.items() if not pic.cards[cid].get("last_date")]
    share = sorted((x["filled"] / x["parts"], x["name"]) for x in r.values())
    from . import reports
    g = reports.gaps(pic, today)
    return {
        "cards": n, "levels": {lv: sum(x["level"] == lv for x in r.values()) for lv in ("ready", "thin", "weak")},
        "current": {"known": n - len(when), "not": when},
        "complete": {"median": round(median(s for s, _ in share), 2) if share else 0.0,
                     "low": [{"name": nm, "share": round(s, 2)} for s, nm in share if s < THIN]},
        "provenance": {"named": sum(x["source"] == "named" for x in r.values()),
                       "memory": [x["name"] for x in r.values() if x["source"] == "memory"],
                       "none": [x["name"] for x in r.values() if x["source"] == "none"]},
        "one_name": {"pairs": [{"a": pic.name(a), "b": pic.name(b), "why": why} for a, b, why in same_names(pic)],
                     "unclear": [{"name": u["name"], "could_be": u["could_be"]} for u in g["unclear_names"]],
                     "no_card": [x["name"] for x in g["named_without_card"]], "areas": areas(pic)},
        "owner": {"named": [x["name"] for x in r.values() if x["owner"]]},
        "by_card": r, "ticks": ticks(runs or []),
    }


def _pct(a: int, b: int) -> str:
    return f"{a} of {b} ({round(100 * a / b)}%)" if b else "none yet"


def check_md(c: dict) -> str:
    n, lv = c["cards"], c["levels"]
    L = ["# Is your picture ready for a model?", "",
         f"Five questions asked of your {n} cards: {lv['ready']} ready, {lv['thin']} thin, {lv['weak']} weak.", ""]
    cur = c["current"]
    L.append(f"1. Does each card say when it was last worked on? {cur['known']} of {n} do."
             + (f" Not: {', '.join(cur['not'])}." if cur["not"] else ""))
    comp = c["complete"]
    L.append(f"2. How much of each card is filled in? Half the cards have {round(100 * comp['median'])}% or more."
             + (" Under 40%: " + ", ".join(f"{x['name']} ({round(100 * x['share'])}%)" for x in comp["low"]) + "."
                if comp["low"] else ""))
    pv = c["provenance"]
    L.append(f"3. Where do its facts come from? {pv['named']} of {n} name a source."
             + (f" From memory only: {', '.join(pv['memory'])}." if pv["memory"] else "")
             + (f" No source: {', '.join(pv['none'])}." if pv["none"] else ""))
    one = c["one_name"]
    bits = [f"\"{p['a']}\" and \"{p['b']}\" may be one project ({p['why']})" for p in one["pairs"]]
    bits += [f"\"{u['name']}\" could be {' or '.join(u['could_be'])}" for u in one["unclear"]]
    bits += [f"\"{x}\" is named but has no card, or a card under another name" for x in one["no_card"]]
    bits += [f"one area written {len(a)} ways: {', '.join(a)}" for a in one["areas"]]
    L.append("4. One name for each thing? " + ("; ".join(bits) + "." if bits else "Yes, as far as kb can tell."))
    ow = c["owner"]["named"]
    L.append(f"5. Who keeps each card true? {len(ow)} of {n} name an owner. Add a line owner: to a card when its "
             "facts belong to someone other than you, such as a client.")
    weak = [x for x in c["by_card"].values() if x["level"] == "weak"]
    if weak:
        L += ["", "## Weak cards, worth fixing first", ""]
        L += [f"- {x['name']}: {'; '.join(x['gaps'])}." for x in weak]
    t = c["ticks"]
    L += ["", "## Does it matter? Your ticks", ""]
    if not t["runs"]:
        L.append("No advice run has recorded its cards' readiness yet. Each run from now on does; rate a few, and "
                 "this shows whether advice from weak cards is advice you act on less.")
    else:
        L.append(f"Pieces resting only on weak cards: you would act on {_pct(t['weak']['acted'], t['weak']['pieces'])}. "
                 f"The rest: {_pct(t['rest']['acted'], t['rest']['pieces'])}. From {t['runs']} run"
                 f"{'s' if t['runs'] != 1 else ''}.")
        if not t["enough"]:
            L.append(f"That is too few to read anything into: kb waits for {MIN_PIECES} rated pieces on each side.")
    return "\n".join(L)
