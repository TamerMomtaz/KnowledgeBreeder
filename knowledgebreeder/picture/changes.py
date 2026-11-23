"""What changed on your cards, and what left them.

Adding a card again used to replace the old one, so an idea that dropped out of a card left no trace. Now nothing is
overwritten: every older version stays in the picture with the day kb learned it and its file's fingerprint, and
this module reads the versions:

    what changed     the newest version against the one before: header lines, items that came and went, needs met
    what left        every idea, need, unfinished piece of work or open decision that was on a card once and is not
                     now, with the day it was last seen. kb cannot tell whether it was done, dropped or forgotten;
                     you can, and a forgotten one is a missed chance found in time.
    files changed    a card whose file has changed since it was added: add it again to see what changed
    sources differ   two cards that may be one project, and say different things about it: both sides are shown,
                     never blended

The rules are old ones from record-keeping: nothing updated in place, two dates per fact, a fingerprint taken at
intake, and both sides of a disagreement shown in neutral words.
"""

from __future__ import annotations

import hashlib
import os

from .cards import met
from .store import Picture, words

WATCH = (("ideas", "IDEAS NOT STARTED", "idea"), ("needs", "WHAT IT NEEDS", "need"),
         ("unfinished", "UNFINISHED", "unfinished work"), ("decisions", "OPEN DECISIONS", "open decision"),
         ("can_do", "WHAT IT CAN DO", "capability"), ("exists", "WHAT EXISTS", "thing made"),
         ("parts", "REUSABLE PARTS", "reusable part"), ("links", "LINKS TO MY OTHER WORK", "link"))
MISSES = ("ideas", "needs", "unfinished", "decisions")    # what may be a missed chance when it leaves a card
HEAD = ("name", "kind", "last_activity", "area", "one_line")
SAME = 0.6                                                # share of words two items hold in common to count as one
NOT_KNOWN = "before kb kept versions"


def fingerprint(text: str | bytes) -> str:
    """A short fingerprint of a file's content: enough to see that it changed, not a seal."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def _norm(item: list[str]) -> frozenset:
    return frozenset(words(item[0] if item else ""))


def _match(item: list[str], pool: list[list[str]]) -> int | None:
    """The index of the same item in ``pool``, reworded or not, or None."""
    a = _norm(item)
    best, at = 0.0, None
    for i, other in enumerate(pool):
        b = _norm(other)
        if not a or not b:
            continue
        share = len(a & b) / len(a | b)
        if share > best:
            best, at = share, i
    return at if best >= SAME else None


def _text(item: list[str]) -> str:
    return " | ".join(item)


def diff(old: dict, new: dict) -> dict:
    """What the newer version of a card says differently from the older one."""
    out: dict = {"fields": [], "gone": [], "new": [], "met": []}
    for f in HEAD:
        if (old.get(f) or "") != (new.get(f) or ""):
            out["fields"].append({"field": f, "was": old.get(f) or "", "now": new.get(f) or ""})
    for key, head, what in WATCH:
        was, now = old.get(key, []), new.get(key, [])
        kept = set()
        for item in was:
            j = _match(item, now)
            if j is None:
                out["gone"].append({"part": key, "head": head, "what": what, "text": _text(item)})
                continue
            kept.add(j)
            if key == "needs" and len(item) > 1 and len(now[j]) > 1 and met(item[1]) != met(now[j][1]):
                out["met"].append({"need": item[0], "was": met(item[1]), "now": met(now[j][1])})
        out["new"] += [{"part": key, "head": head, "what": what, "text": _text(x)}
                       for j, x in enumerate(now) if j not in kept]
    return out


def versions(pic: Picture, cid: str) -> list[dict]:
    """Every version of a card, oldest first, the current one last."""
    return [*pic.history.get(cid, []), pic.cards[cid]]


def left(pic: Picture, cid: str) -> list[dict]:
    """Ideas, needs, unfinished work and open decisions that were on the card once and are not now."""
    vs = versions(pic, cid)
    now = vs[-1]
    out: list[dict] = []
    for key, head, what in WATCH:
        if key not in MISSES:
            continue
        gone: list[dict] = []
        for i, v in enumerate(vs[:-1]):
            for item in v.get(key, []):
                if _match(item, now.get(key, [])) is not None:
                    continue
                g = next((g for g in gone if _match(item, [g["item"]]) is not None), None)
                if g is None:
                    g = {"item": item}
                    gone.append(g)
                g["item"] = item                                        # the newest wording it had
                g["last_seen"] = v.get("recorded") or NOT_KNOWN
                g["gone_since"] = vs[i + 1].get("recorded") or NOT_KNOWN
        out += [{"name": now["name"], "id": cid, "part": key, "head": head, "what": what, "text": _text(g["item"]),
                 "last_seen": g["last_seen"], "gone_since": g["gone_since"]} for g in gone]
    return out


def left_all(pic: Picture) -> list[dict]:
    """What left any card, the most recent first."""
    out = [x for cid in pic.history if cid in pic.cards for x in left(pic, cid)]
    return sorted(out, key=lambda x: x["gone_since"] if x["gone_since"] != NOT_KNOWN else "", reverse=True)


def stale(pic: Picture) -> list[dict]:
    """Cards whose file has changed since kb read it. A file that is gone is not counted: downloads get cleared."""
    out = []
    for c in pic.cards.values():
        path, fp = c.get("origin") or "", c.get("fingerprint") or ""
        if not fp or not path or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            if fingerprint(f.read()) != fp:
                out.append({"name": c["name"], "origin": path})
    return out


def differ(pic: Picture) -> list[dict]:
    """Two cards that may be one project and say different things about it, with both sides and where each came from."""
    from .check import same_names
    out = []
    for a, b, why in same_names(pic):
        ca, cb = pic.cards[a], pic.cards[b]
        for f in ("kind", "last_activity"):
            va, vb = (ca.get(f) or "").strip(), (cb.get(f) or "").strip()
            if va and vb and va.lower() != vb.lower():
                out.append({"a": ca["name"], "b": cb["name"], "field": f, "a_says": va, "b_says": vb,
                            "a_from": os.path.basename(ca.get("origin") or "") or "unknown",
                            "b_from": os.path.basename(cb.get("origin") or "") or "unknown", "why": why})
    return out


def changes(pic: Picture, project: str | None = None) -> dict:
    ids = [project] if project else [cid for cid in pic.cards if pic.history.get(cid)]
    by_card = {}
    for cid in ids:
        vs = versions(pic, cid)
        by_card[cid] = {"name": pic.name(cid), "versions": len(vs),
                        "dates": [v.get("recorded") or NOT_KNOWN for v in vs],
                        "last": diff(vs[-2], vs[-1]) if len(vs) > 1 else None, "left": left(pic, cid)}
    return {"cards": len(pic.cards), "with_history": sum(bool(pic.history.get(c)) for c in pic.cards),
            "by_card": by_card, "left": [x for c in by_card.values() for x in c["left"]],
            "stale": stale(pic), "differ": differ(pic)}


def line(d: dict) -> str:
    """One line on what a new version changed, for kb picture add."""
    bits = []
    if d["gone"]:
        bits.append(f"{len(d['gone'])} left the card ("
                    + "; ".join(f"{g['what']}: {g['text'].split(' | ')[0]}" for g in d["gone"][:3])
                    + ("; …" if len(d["gone"]) > 3 else "") + ")")
    if d["new"]:
        bits.append(f"{len(d['new'])} new")
    if d["met"]:
        bits.append("; ".join(f"need {m['need']}: {m['was']} → {m['now']}" for m in d["met"][:2]))
    if d["fields"]:
        bits.append(", ".join(f"{f['field']} {f['was'] or '(none)'} → {f['now'] or '(none)'}" for f in d["fields"][:2]))
    return ". ".join(bits) or "reworded only"


def changes_md(c: dict) -> str:
    L = ["# What changed on your cards", ""]
    if not c["with_history"] and not c["by_card"]:
        L.append(f"None of your {c['cards']} cards has an older version yet. From now on, adding a card again keeps "
                 "the one before, and this page shows what changed and what left it.")
    else:
        L.append(f"{c['with_history']} of your {c['cards']} cards have older versions. Nothing is overwritten.")
    if c["left"]:
        L += ["", "## No longer on a card", "",
              "Each was on a card once and is not now. kb cannot tell whether it was done, dropped or forgotten.", ""]
        L += [f"- {x['name']}, {x['what']}: {x['text']} (last seen {x['last_seen']}, gone since {x['gone_since']})"
              for x in c["left"]]
    shown = [x for x in c["by_card"].values() if x["last"]]
    if shown:
        L += ["", "## The newest version against the one before", ""]
        for x in shown:
            d = x["last"]
            L.append(f"### {x['name']} ({x['versions']} versions: {', '.join(x['dates'])})")
            L += [f"- {f['field']}: was \"{f['was']}\", now \"{f['now']}\"" for f in d["fields"]]
            L += [f"- left, {g['what']}: {g['text']}" for g in d["gone"]]
            L += [f"- new, {g['what']}: {g['text']}" for g in d["new"]]
            L += [f"- need {m['need']}: was {m['was']}, now {m['now']}" for m in d["met"]]
            if not (d["fields"] or d["gone"] or d["new"] or d["met"]):
                L.append("- reworded only")
            L.append("")
    if c["stale"]:
        L += ["", "## Files changed since you added them", ""]
        L += [f"- {s['name']}: {s['origin']}. Add it again to see what changed." for s in c["stale"]]
    if c["differ"]:
        L += ["", "## Where two cards that may be one project differ", "",
              "Both sides are shown. Neither is taken as right.", ""]
        L += [f"- {d['field']}: \"{d['a']}\" says {d['a_says']} ({d['a_from']}); \"{d['b']}\" says {d['b_says']} "
              f"({d['b_from']})" for d in c["differ"]]
    return "\n".join(L).rstrip() + "\n"
