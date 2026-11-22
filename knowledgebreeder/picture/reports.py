"""Four readings of a picture: overlaps, gaps, reuse, and a short brief built from them.

Everything here is counting and word matching over the cards. Nothing calls a
model and nothing looks outside the picture. Each line names the card and the
heading it came from, so a person can check it. A "word match" is a hint to
look, not a finding.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from itertools import combinations

from .cards import by_what, met
from .store import Picture, words

_CUES = re.compile(r"\b(same|both|overlap\w*|also|second|cop(?:y|ies|ied)|earlier form|later form|rebuil[dt]|"
                   r"built separately|generated|duplicate\w*|twin|competes?)\b", re.I)
_WIDE = re.compile(r"\b(every|any|all|anywhere|everything)\b", re.I)


# ---- overlaps -----------------------------------------------------------------------------------------------
def _theme_clusters(pic: Picture) -> list[dict]:
    items = []                                           # (card id, phrase, word set)
    for cid, c in pic.cards.items():
        for f in c["themes"]:
            phrase = f[0].strip().rstrip(".")
            ws = frozenset(words(phrase))
            if ws:
                items.append((cid, phrase, ws))
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in combinations(range(len(items)), 2):
        a, b = items[i][2], items[j][2]
        if a == b or a < b or b < a or len(a & b) >= 2:  # the same words, one phrase inside the other, or two shared
            parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(items)):
        groups[find(i)].append(items[i])
    out = []
    for g in groups.values():
        projects = sorted({pic.name(cid) for cid, _p, _w in g})
        if len(projects) > 1:
            label = min((p for _c, p, _w in g), key=lambda p: (len(words(p)), len(p)))
            out.append({"theme": label, "projects": projects,
                        "phrases": sorted({p for _c, p, _w in g}), "ids": sorted({cid for cid, _p, _w in g})})
    return sorted(out, key=lambda t: (-len(t["projects"]), t["theme"].lower()))


def _docs(pic: Picture) -> dict[str, list[str]]:
    docs = {}
    for cid, c in pic.cards.items():
        text = [c["one_line"], c["purpose"].get("problem", "")]
        text += [f[0] for f in c["exists"]] + [" ".join(f) for f in c["can_do"]] + [f[0] for f in c["parts"]]
        docs[cid] = words(" ".join(text))
    return docs


def overlaps(pic: Picture, top: int = 10, floor: float = 0.2) -> dict:
    by_pair: dict[tuple, dict] = {}
    for link in pic.links():
        if link["to"] and _CUES.search(link["how"]):
            for t in link["to"]:
                pair = tuple(sorted((link["from"], t)))
                row = by_pair.setdefault(pair, {"a": pic.name(link["from"]), "b": pic.name(t), "says": link["how"],
                                                "ids": list(pair)})
                if link["how"] not in row["says"]:
                    row["says"] += " / " + link["how"]
    stated, seen = list(by_pair.values()), set(by_pair)

    docs = _docs(pic)
    idf = pic.idf(docs)
    weight = {cid: {w: idf[w] for w in set(d) if idf[w] > 0} for cid, d in docs.items()}
    norm = {cid: math.sqrt(sum(v * v for v in ws.values())) for cid, ws in weight.items()}
    similar = []
    for a, b in combinations(pic.cards, 2):
        shared = set(weight[a]) & set(weight[b])
        if len(shared) < 4 or not norm[a] or not norm[b] or tuple(sorted((a, b))) in seen:
            continue
        score = sum(weight[a][w] ** 2 for w in shared) / (norm[a] * norm[b])
        if score >= floor:
            similar.append({"a": pic.name(a), "b": pic.name(b), "score": round(score, 3), "ids": [a, b],
                            "shared": sorted(shared, key=lambda w: (-idf[w], w))[:8]})
    similar.sort(key=lambda s: -s["score"])
    return {"themes": _theme_clusters(pic), "stated": stated, "similar": similar[:top]}


# ---- gaps ---------------------------------------------------------------------------------------------------
def gaps(pic: Picture, today: date | None = None, quiet_days: int = 90) -> dict:
    today = today or date.today()
    needs, unfinished, decisions, unseen, quiet, unknown, empty = [], [], [], [], [], [], []
    for cid, c in pic.cards.items():
        n = c["name"]
        for f in c["needs"]:
            state = met(f[1]) if len(f) > 1 else "unknown"
            if state != "yes":
                needs.append({"project": n, "id": cid, "need": f[0], "met": state, "by": by_what(f)})
        for f in c["unfinished"]:
            unfinished.append({"project": n, "id": cid, "what": f[0], "detail": " | ".join(f[1:])})
        for f in c["decisions"]:
            decisions.append({"project": n, "id": cid, "decision": " | ".join(f)})
        for f in c["unseen"]:
            unseen.append({"project": n, "id": cid, "what": " | ".join(f)})
        if c.get("last_date"):
            days = (today - date.fromisoformat(c["last_date"])).days
            if days > quiet_days:
                quiet.append({"project": n, "id": cid, "last": c["last_date"], "days": days, "kind": c["kind"]})
        else:
            quiet.append({"project": n, "id": cid, "last": None, "days": None, "kind": c["kind"]})
        if c["unknown"]:
            unknown.append({"project": n, "id": cid, "unknown": c["unknown"]})

    named: dict[str, dict] = {}
    unclear: dict[str, dict] = {}
    linked = set()
    for link in pic.links():
        if link["to"]:
            linked.add(link["from"])
            linked.update(link["to"])
        elif not link["collective"]:
            book, extra = (unclear, {"could_be": [pic.name(t) for t in link["unclear"]]}) if link["unclear"] else (named, {})
            row = book.setdefault(link["target"].lower(), {"name": link["target"], "named_by": [], **extra})
            if pic.name(link["from"]) not in row["named_by"]:
                row["named_by"].append(pic.name(link["from"]))
    alone = [{"project": c["name"], "id": cid} for cid, c in pic.cards.items() if cid not in linked]
    empty = [a for a, cs in pic.by_area().items() if not cs]
    quiet.sort(key=lambda q: -(q["days"] if q["days"] is not None else 10 ** 6))
    return {"today": today.isoformat(), "quiet_days": quiet_days, "unmet_needs": needs, "unfinished": unfinished,
            "open_decisions": decisions, "named_without_card": sorted(named.values(), key=lambda x: x["name"].lower()),
            "unclear_names": sorted(unclear.values(), key=lambda x: x["name"].lower()),
            "empty_areas": empty, "standing_alone": alone, "quiet": quiet, "unknown": unknown, "not_seen": unseen}


# ---- reuse --------------------------------------------------------------------------------------------------
def reuse(pic: Picture, top: int = 12, floor: float = 2.0) -> dict:
    wants: list[tuple[str, str, str, list[str]]] = []      # (card id, heading, text, words)
    for cid, c in pic.cards.items():
        for key, head in (("needs", "WHAT IT NEEDS"), ("unfinished", "UNFINISHED"), ("ideas", "IDEAS NOT STARTED")):
            for f in c[key]:
                if key == "needs" and len(f) > 1:
                    if met(f[1]) == "yes":
                        continue
                wants.append((cid, head, f[0], words(f[0])))
    docs = {f"{cid}:{i}": w for i, (cid, _h, _t, w) in enumerate(wants)}
    for cid, c in pic.cards.items():
        for i, f in enumerate(c["parts"]):
            docs[f"p:{cid}:{i}"] = words(" ".join(f))
    idf = pic.idf(docs)

    named, matched, wide = [], [], []
    for cid, c in pic.cards.items():
        for f in c["parts"]:
            part, why = f[0], " | ".join(f[1:])
            targets = pic.mentions(why, skip=cid)
            for t in targets:
                named.append({"part": part, "from": c["name"], "to": pic.name(t), "why": why,
                              "basis": "the card says so", "ids": [cid, t]})
            if _WIDE.search(why) and not targets:
                wide.append({"part": part, "from": c["name"], "why": why, "id": cid})
            pw = set(words(part + " " + why))
            for wid, head, text, ww in wants:
                if wid == cid or wid in targets:
                    continue
                shared = pw & set(ww)
                score = sum(idf.get(w, 0) for w in shared)
                if len(shared) >= 2 and score >= floor:
                    matched.append({"part": part, "from": c["name"], "to": pic.name(wid), "for": text, "heading": head,
                                    "shared": sorted(shared), "score": round(score, 2),
                                    "basis": "word match", "ids": [cid, wid]})
    matched.sort(key=lambda m: -m["score"])
    return {"named": named, "matched": matched[:top], "wide": wide}


# ---- brief --------------------------------------------------------------------------------------------------
def brief(pic: Picture, today: date | None = None, top: int = 9) -> list[dict]:
    """A short list of moves worth a look, each with why and where it came from. Rules only, no model."""
    ov, gp, ru = overlaps(pic), gaps(pic, today), reuse(pic)
    out: list[dict] = []
    by_target = defaultdict(list)
    for r in ru["named"]:
        by_target[r["to"]].append(r)
    for target, rs in sorted(by_target.items(), key=lambda kv: -len(kv[1]))[:2]:
        parts = "; ".join(f"{r['part']} (from {r['from']})" for r in rs[:4])
        out.append({"move": f"Before building more in {target}, lift what already exists: {parts}.",
                    "why": (f"{len(rs)} of your own cards name {target} as a place their part could serve."
                            if len(rs) > 1 else f"One of your own cards names {target} as a place its part could serve."),
                    "source": [f"{r['from']} · REUSABLE PARTS" for r in rs[:4]], "kind": "reuse"})
    for t in [t for t in ov["themes"] if len(t["projects"]) >= 3][:2]:
        out.append({"move": f"Decide which project holds the shared version of \"{t['theme']}\".",
                    "why": f"It shows up in {len(t['projects'])} projects: {', '.join(t['projects'])}.",
                    "source": [f"{p} · RECURRING THEMES" for p in t["projects"]], "kind": "overlap"})
    quiet = {q["id"] for q in gp["quiet"]}
    live = sorted(ov["stated"], key=lambda s: sum(i in quiet for i in s["ids"]))    # both still worked on first
    for s in live[:2]:
        out.append({"move": f"Look at {s['a']} and {s['b']} side by side.",
                    "why": f"The card says: {s['says']}.", "source": [f"{s['a']} · LINKS TO MY OTHER WORK"],
                    "kind": "overlap"})
    for n in [n for n in gp["unmet_needs"] if n["met"] in ("no", "partly")][:2]:
        help_ = next((m for m in ru["matched"] if m["to"] == n["project"] and m["for"] == n["need"]), None)
        why = f"Marked as {'not met' if n['met'] == 'no' else 'partly met'}" + (f": {n['by']}." if n["by"] else ".")
        if help_:
            why += f" Possible help: {help_['part']} in {help_['from']} (word match, check it)."
        out.append({"move": f"{n['project']} is waiting on: {n['need']}.", "why": why,
                    "source": [f"{n['project']} · WHAT IT NEEDS"], "kind": "gap"})
    for d in gp["open_decisions"][:2]:
        out.append({"move": f"Decide, for {d['project']}: {d['decision']}", "why": "It is listed as waiting on you.",
                    "source": [f"{d['project']} · OPEN DECISIONS"], "kind": "decision"})
    from .changes import left_all
    for x in left_all(pic)[:2]:
        out.append({"move": f"Look again at what left {x['name']}: {x['text'].split(' | ')[0]}.",
                    "why": f"It was on the card as {'an' if x['what'][0] in 'aeiou' else 'a'} {x['what']} until "
                           f"{x['last_seen']} and is not on it now. kb cannot tell whether it was done, dropped or "
                           "forgotten.",
                    "source": [f"{x['name']} · older version"], "kind": "left"})
    if gp["named_without_card"]:
        names = ", ".join(x["name"] for x in gp["named_without_card"][:5])
        out.append({"move": f"Add a card for: {names}.",
                    "why": "Your cards name them, but the picture holds nothing about them.",
                    "source": sorted({f"{b} · LINKS TO MY OTHER WORK" for x in gp["named_without_card"][:5]
                                      for b in x["named_by"]}), "kind": "gap"})
    no_goal = [u["project"] for u in gp["unknown"] if "my_goal" in u["unknown"]]
    if no_goal:
        out.append({"move": f"Say what you want from: {', '.join(no_goal[:6])}"
                            + (f" and {len(no_goal) - 6} more." if len(no_goal) > 6 else "."),
                    "why": "Their cards hold no goal in your own words, so nothing can be ranked against it.",
                    "source": [f"{p} · PURPOSE" for p in no_goal[:6]], "kind": "question"})
    if gp["empty_areas"]:
        out.append({"move": f"Tell the picture about: {', '.join(gp['empty_areas'])}.",
                    "why": "You named these areas and no card describes them yet.", "source": [], "kind": "question"})
    return out[:top]


# ---- text ---------------------------------------------------------------------------------------------------
NOTE = "Counted and word-matched from your own cards. A word match is a hint to look, not a finding."


def overlaps_md(o: dict) -> str:
    L = ["# Overlaps", "", NOTE, "", "## The same idea in more than one project"]
    L += [f"- **{t['theme']}** ({len(t['projects'])}): {', '.join(t['projects'])}" for t in o["themes"]] or ["- none found"]
    L += ["", "## Overlaps the cards state themselves"]
    L += [f"- {s['a']} and {s['b']}: {s['says']}" for s in o["stated"]] or ["- none stated"]
    L += ["", "## Described in similar words (word match)"]
    L += [f"- {s['a']} and {s['b']} ({s['score']}): {', '.join(s['shared'])}" for s in o["similar"]] or ["- none found"]
    return "\n".join(L)


def gaps_md(g: dict) -> str:
    L = ["# Gaps", "", f"As of {g['today']}.", "", "## Needs not met"]
    L += [f"- {n['project']}: {n['need']} ({n['met']}{', ' + n['by'] if n['by'] else ''})" for n in g["unmet_needs"]] or ["- none listed"]
    L += ["", "## Started and not finished"]
    L += [f"- {u['project']}: {u['what']}" + (f" ({u['detail']})" if u["detail"] else "") for u in g["unfinished"]] or ["- none listed"]
    L += ["", "## Decisions waiting on you"]
    L += [f"- {d['project']}: {d['decision']}" for d in g["open_decisions"]] or ["- none listed"]
    L += ["", "## Named in a card, but no card of its own"]
    L += [f"- {x['name']} (named by {', '.join(x['named_by'])})" for x in g["named_without_card"]] or ["- none"]
    L += ["", "## A name that fits more than one card"]
    L += [f"- {x['name']} (named by {', '.join(x['named_by'])}): could be {' or '.join(x['could_be'])}"
          for x in g["unclear_names"]] or ["- none"]
    L += ["", "## Areas with no card"] + ([f"- {a}" for a in g["empty_areas"]] or ["- none"])
    L += ["", "## Tied to nothing else"] + ([f"- {a['project']}" for a in g["standing_alone"]] or ["- none"])
    L += ["", f"## Quiet for more than {g['quiet_days']} days"]
    L += [f"- {q['project']}: " + (f"last work {q['last']}, {q['days']} days ago" if q["last"] else "no date given")
          for q in g["quiet"]] or ["- none"]
    L += ["", "## Left as unknown"]
    L += [f"- {u['project']}: {', '.join(u['unknown'])}" for u in g["unknown"]] or ["- none"]
    L += ["", "## What the card's writer could not see"]
    L += [f"- {u['project']}: {u['what']}" for u in g["not_seen"]] or ["- none listed"]
    return "\n".join(L)


def reuse_md(r: dict) -> str:
    L = ["# Reuse", "", NOTE, "", "## A part one card offers to a named project"]
    L += [f"- **{x['part']}**, from {x['from']} to {x['to']}: {x['why']}" for x in r["named"]] or ["- none named"]
    L += ["", "## A part that may answer a need elsewhere (word match)"]
    L += [f"- **{x['part']}** ({x['from']}) for {x['to']}, \"{x['for']}\": shared words {', '.join(x['shared'])}"
          for x in r["matched"]] or ["- none found"]
    L += ["", "## Parts offered to everything"]
    L += [f"- **{x['part']}** ({x['from']}): {x['why']}" for x in r["wide"]] or ["- none"]
    return "\n".join(L)


def brief_md(items: list[dict]) -> str:
    L = ["# Brief", "", "Moves worth a look, from rules over your own cards. It does not look outside the picture.", ""]
    for i, b in enumerate(items, 1):
        L.append(f"{i}. {b['move']}")
        L.append(f"   Why: {b['why']}")
        if b["source"]:
            L.append(f"   From: {'; '.join(b['source'])}")
    if not items:
        L.append("Nothing to raise yet. Add more cards.")
    return "\n".join(L)


def summary(pic: Picture) -> dict:
    return {"cards": len(pic.cards), "areas": {a: len(cs) for a, cs in pic.by_area().items()},
            "newest_work": pic.newest(),
            "links": sum(1 for link in pic.links() if link["to"])}
