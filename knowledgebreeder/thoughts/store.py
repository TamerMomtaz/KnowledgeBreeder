"""The map of thoughts: one private file, work/thoughts.json, that every source adds to and nothing overwrites.

    source      where thoughts came from: a card, a framed book, an inbox item
    thought     one idea, said in one sentence, with the source and the words it came from
    role        what the thought is in the city: infrastructure, a resource, a utility, or a need
    link        two thoughts joined: needs, causes, is part of, contradicts (said by a model or by you, and
                held to the source), or "may help" (found by kb from shared words: a hint, not a finding)
    marriage    two thoughts that could make a new one. It joins the map only when you approve it.

Cards and framed books are read by rules, at once, every time a command runs. Inbox items wait for a model
(see read.py). Whenever a thought arrives, kb links it at once, by shared words, to the thoughts already on the map
from other sources that may help it or that it may help.

Nothing is overwritten. A thought whose card line is gone is kept and marked with the day it left; a declined
marriage is kept, so it is never proposed again.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from ..picture import private as _private
from ..picture.cards import met
from ..picture.store import words

VERSION = 1
DEFAULT_PATH = "work/thoughts.json"
ROLES = ("infrastructure", "resource", "utility", "need")
JOINS = ("needs", "causes", "is part of", "contradicts")      # said by a model or by you, held to a source
HINT = "may help"                                             # found by kb from shared words
KINDS = JOINS + (HINT,)
CARDS_SUBJECT = "My projects"
MARRIED_SUBJECT = "Married thoughts"
STATES = ("proposed", "approved", "declined", "no child")
MAX_HINTS = 3                       # word links made for one new thought
MIN_SHARED = 2                      # telling words two thoughts must share before kb links them

# what each heading of a card is, as a thought in the city
CARD_ROLES = (("themes", "RECURRING THEMES", "infrastructure"), ("ideas", "IDEAS NOT STARTED", "infrastructure"),
              ("can_do", "WHAT IT CAN DO", "utility"), ("parts", "REUSABLE PARTS", "utility"),
              ("exists", "WHAT EXISTS", "resource"), ("needs", "WHAT IT NEEDS", "need"))

_JOIN_WORDS = {"needs": "needs", "need": "needs", "requires": "needs", "causes": "causes", "cause": "causes",
               "leads to": "causes", "is part of": "is part of", "part of": "is part of", "part_of": "is part of",
               "is_part_of": "is part of", "contradicts": "contradicts", "contradict": "contradicts"}


def join_kind(raw: Any) -> str | None:
    """One of the four joins, from the ways a model (or a person) may write it, or None."""
    return _JOIN_WORDS.get(" ".join(str(raw or "").lower().replace("-", " ").split()))


def flat(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:7]


def met_field(text: str) -> bool:
    """True for the "met? no" part of a need: it says how far, not what."""
    return flat(text).startswith(("met", "is it met"))


def _unknown(text: str) -> bool:
    return not text or flat(text).startswith("unknown") or len(text.strip()) < 4


class Map:
    """The map, read from and written to one JSON file."""

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        data = self._read()
        self.sources: dict[str, dict] = data.get("sources", {})
        self.thoughts: dict[str, dict] = data.get("thoughts", {})
        self.links: list[dict] = data.get("links", [])
        self.marriages: dict[str, dict] = data.get("marriages", {})

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".part")
        data = {"version": VERSION, "sources": self.sources, "thoughts": self.thoughts, "links": self.links,
                "marriages": self.marriages}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path

    # ---- reading the map ----------------------------------------------------------------------------------
    def live(self) -> dict[str, dict]:
        """The thoughts still standing: not left their source."""
        return {k: t for k, t in self.thoughts.items() if not t.get("left")}

    def get(self, tid: str) -> dict:
        t = self.thoughts.get((tid or "").strip())
        if not t:
            raise KeyError(f"no thought {tid!r} on the map. See them with: kb thoughts show --all")
        return t

    def subjects(self) -> list[str]:
        return sorted({t["subject"] for t in self.live().values()}, key=str.lower)

    def linked(self, a: str, b: str) -> dict | None:
        for ln in self.links:
            if {ln["a"], ln["b"]} == {a, b}:
                return ln
        return None

    def links_of(self, tid: str) -> list[dict]:
        return [ln for ln in self.links if tid in (ln["a"], ln["b"])]

    def degree(self) -> Counter:
        live = self.live()
        deg: Counter = Counter({k: 0 for k in live})
        for ln in self.links:
            if ln["a"] in live and ln["b"] in live:
                deg[ln["a"]] += 1
                deg[ln["b"]] += 1
        return deg

    def source_title(self, sid: str) -> str:
        s = self.sources.get(sid) or {}
        return s.get("title") or sid

    # ---- adding -------------------------------------------------------------------------------------------
    def add_source(self, sid: str, **fields: Any) -> dict:
        s = self.sources.setdefault(sid, {"id": sid})
        s.update({k: v for k, v in fields.items() if v is not None})
        return s

    def add_thought(self, text: str, role: str, subject: str, source: str, where: str, today: date, by: str,
                    quote: str = "", private: bool = False, **extra: Any) -> tuple[str, bool]:
        """(id, new). The same words from the same place are one thought; one that had left comes back."""
        text = " ".join(str(text).split())[:500]
        tid = _id("t", source, where, flat(text))
        if tid in self.thoughts:
            t = self.thoughts[tid]
            back = bool(t.pop("left", None))
            return tid, back
        self.thoughts[tid] = {"id": tid, "text": text, "role": role if role in ROLES else "resource",
                              "subject": subject, "source": source, "from": where, "quote": quote[:1200],
                              "by": by, "added": today.isoformat(), **({"private": True} if private else {}), **extra}
        return tid, True

    def add_link(self, a: str, b: str, kind: str, by: str, today: date, why: str = "", quote: str = "",
                 shared: list[str] | None = None) -> dict | None:
        """One link. A pair holds one link said by a model or a person; a word hint gives way to it."""
        if a == b or a not in self.thoughts or b not in self.thoughts or kind not in KINDS:
            return None
        old = self.linked(a, b)
        if old:
            if old["kind"] == HINT and kind != HINT:
                self.links.remove(old)
            else:
                return None
        ln = {"a": a, "b": b, "kind": kind, "by": by, "added": today.isoformat(), "why": why[:400]}
        if quote:
            ln["quote"] = quote[:1200]
        if shared:
            ln["shared"] = shared
        self.links.append(ln)
        return ln

    def hint_links(self, new: list[str], today: date) -> int:
        """Link each new thought, by its most telling shared words, to thoughts from other sources. Returns how
        many links were made. A need is helped; anything else is helped by what was there before it."""
        live = self.live()
        docs = {k: set(words(f"{t['text']} {t.get('quote', '')}")) for k, t in live.items()}
        n = max(len(docs), 1)
        df = Counter(w for d in docs.values() for w in d)
        idf = {w: math.log(n / k) for w, k in df.items()}
        index: dict[str, set[str]] = defaultdict(set)
        for k, d in docs.items():
            for w in d:
                index[w].add(k)
        made = 0
        for tid in new:
            if tid not in live:
                continue
            mine = docs[tid]
            near: Counter = Counter()
            for w in mine:
                if idf.get(w, 0) > 0:
                    for other in index[w]:
                        near[other] += 1
            scored = []
            for other, count in near.items():
                if other == tid or count < MIN_SHARED or live[other]["source"] == live[tid]["source"]:
                    continue
                shared = sorted(mine & docs[other], key=lambda w: (-idf.get(w, 0), w))
                scored.append((-sum(idf.get(w, 0) for w in shared), other, shared))
            for _, other, shared in sorted(scored)[:MAX_HINTS]:
                helper, helped = other, tid
                if live[other]["role"] == "need" and live[tid]["role"] != "need":
                    helper, helped = tid, other
                if self.add_link(helper, helped, HINT, "words", today, shared=shared[:6]):
                    made += 1
        return made


# ---- what arrives by rules: cards and framed books, and inbox items waiting for a model ------------------------
def from_cards(m: Map, pic, today: date) -> list[str]:
    """Every card as thoughts in one subject. A card line that is gone marks its thought as left; none is deleted."""
    new, seen = [], set()
    for cid, c in pic.cards.items():
        sid = f"card:{cid}"
        private = _private.marked(f"{c['name']} {c['one_line']}")
        m.add_source(sid, kind="card", title=c["name"], subject=CARDS_SUBJECT, status="read",
                     private=True if private else None)
        for key, head, role in CARD_ROLES:
            for f in c.get(key) or []:
                text = str(f[0]).strip() if f else ""
                if _unknown(text):
                    continue
                if key == "needs" and len(f) > 1 and met(f[1]) == "yes":
                    continue
                tid, fresh = m.add_thought(text, role, CARDS_SUBJECT, sid, f"{c['name']} · {head}", today, "card",
                                           quote=" | ".join(str(x) for x in f[1:] if not met_field(str(x))),
                                           private=private)
                seen.add(tid)
                if fresh:
                    new.append(tid)
    for tid, t in m.thoughts.items():
        if t["source"].startswith("card:") and tid not in seen and not t.get("left"):
            t["left"] = today.isoformat()
    return new


def from_books(m: Map, folder: str | Path, today: date) -> list[str]:
    """The principles of every framed book, each book its own subject. A book on the shelf not yet framed waits."""
    folder, new = Path(folder), []
    if not folder.is_dir():
        return new
    try:
        shelf = json.loads((folder / "shelf.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        shelf = {}
    for key, entry in (shelf.items() if isinstance(shelf, dict) else []):
        if isinstance(entry, dict) and entry.get("status") == "waiting":
            m.add_source(f"book:{key}", kind="book", title=entry.get("title") or key, status="waits_frame")
    for p in sorted(folder.glob("*.json")):
        if p.name == "shelf.json":
            continue
        try:
            f = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(f, dict) or not f.get("known") or not f.get("framework"):
            continue
        title = str(f.get("title") or p.stem)
        sid = f"book:{p.stem}"
        m.add_source(sid, kind="book", title=title, subject=title, status="read",
                     by=f"the frame-outer with {f.get('worker', '?')}")
        for pr in f["framework"]:
            name, says = str(pr.get("name") or "").strip(), str(pr.get("says") or "").strip()
            if not name:
                continue
            tid, fresh = m.add_thought(f"{name}: {says}" if says else name, "infrastructure", title, sid,
                                       f"{title} · principle", today, "book",
                                       quote=str(pr.get("use") or ""))
            if fresh:
                new.append(tid)
    return new


def from_inbox(m: Map, inbox, today: date) -> int:
    """Register every inbox item. One with text waits for a model to read it (kb thoughts read); a screenshot or a
    voice note waits for a reader on this laptop. Returns how many items newly wait."""
    waiting = 0
    for item in inbox.items():
        sid = f"inbox:{item['id']}"
        title = item.get("name") or (item.get("preview") or "")[:80] or item["id"]
        text = inbox.text(item) if item.get("text_file") else ""
        if item.get("status") in ("waits_image", "waits_speech") and not text.strip():
            m.add_source(sid, kind="inbox", title=title, ref=item["id"], status="waits_reader",
                         why="waits for an image reader" if item["status"] == "waits_image" else
                         "waits for a speech reader")
            continue
        if not text.strip():
            continue
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        old = m.sources.get(sid)
        if old and old.get("sha") == sha:
            continue
        if not old or old.get("status") != "waits_model":
            waiting += 1
        m.add_source(sid, kind="inbox", title=title, ref=item["id"], sha=sha, status="waits_model",
                     received=item.get("received"))
    return waiting


def gather(m: Map, pic=None, books: str | Path | None = None, inbox=None, today: date | None = None) -> dict:
    """Everything rules can bring in, at once, and the word links for every new thought."""
    today = today or date.today()
    new = from_cards(m, pic, today) if pic is not None else []
    new += from_books(m, books, today) if books else []
    waiting = from_inbox(m, inbox, today) if inbox is not None else 0
    links = m.hint_links(new, today)
    return {"new": len(new), "links": links, "waiting": waiting}


# ---- marriages ----------------------------------------------------------------------------------------------
def pair_id(a: str, b: str) -> str:
    return _id("m", *sorted((a, b)))


def candidates(m: Map, limit: int = 10, guard: _private.Private | None = None) -> list[dict]:
    """Pairs that could marry: two standing thoughts from different subjects, already joined, never asked before.
    A join said by a model or by you comes first, then the word hints with the most telling words."""
    live, out = m.live(), []
    for ln in m.links:
        a, b = live.get(ln["a"]), live.get(ln["b"])
        if not a or not b or a["subject"] == b["subject"] or ln["kind"] == "contradicts":
            continue
        if pair_id(a["id"], b["id"]) in m.marriages:
            continue
        if guard and any(t.get("private") or guard.holds(f"{t['text']} {t['subject']}") for t in (a, b)):
            continue
        out.append({"id": pair_id(a["id"], b["id"]), "a": a["id"], "b": b["id"], "kind": ln["kind"],
                    "said": ln["kind"] != HINT, "shared": ln.get("shared", [])})
    out.sort(key=lambda c: (not c["said"], -len(c["shared"]), c["id"]))
    return out[:limit]


def propose(m: Map, a: str, b: str, child: str, role: str, why: str, by: str, today: date, state: str = "proposed",
            notes: list[str] | None = None) -> dict:
    mid = pair_id(a, b)
    rec = {"id": mid, "a": a, "b": b, "child": " ".join(str(child).split())[:500],
           "role": role if role in ROLES else "infrastructure", "why": why[:400], "by": by, "state": state,
           "proposed": today.isoformat()}
    if notes:
        rec["notes"] = notes
    m.marriages[mid] = rec
    return rec


def approve(m: Map, mid: str, today: date) -> str:
    """Your yes: the child becomes a thought, in the married district, and is linked at once like any newcomer."""
    rec = m.marriages.get((mid or "").strip())
    if not rec:
        raise KeyError(f"no marriage {mid!r}. See the ones waiting with: kb thoughts marry")
    if rec["state"] == "approved" and rec.get("child_id") in m.thoughts:
        return rec["child_id"]
    if not rec.get("child"):
        raise KeyError(f"{mid} has no child to approve. Write one yourself: kb thoughts marry {rec['a']} {rec['b']} "
                       "--as \"the new thought\"")
    pa, pb = m.get(rec["a"]), m.get(rec["b"])
    tid, _ = m.add_thought(rec["child"], rec["role"], MARRIED_SUBJECT, f"marriage:{mid}",
                           f"{pa['text'][:60]} + {pb['text'][:60]}", today, "marriage", parents=[pa["id"], pb["id"]],
                           private=bool(pa.get("private") or pb.get("private")))
    m.add_source(f"marriage:{mid}", kind="marriage", title=f"Marriage {mid}", subject=MARRIED_SUBJECT, status="read")
    rec.update(state="approved", approved=today.isoformat(), child_id=tid)
    m.hint_links([tid], today)
    return tid


def decline(m: Map, mid: str, today: date) -> dict:
    rec = m.marriages.get((mid or "").strip())
    if not rec:
        raise KeyError(f"no marriage {mid!r}. See the ones waiting with: kb thoughts marry")
    if rec["state"] == "approved":
        raise KeyError(f"{mid} is approved already; its child stays on the map.")
    rec.update(state="declined", declined=today.isoformat())
    return rec


def marry_by_hand(m: Map, a: str, b: str, child: str, today: date) -> str:
    """You write the child yourself, so it needs no approval."""
    m.get(a), m.get(b)
    if not child.strip():
        raise KeyError('say the new thought: kb thoughts marry T1 T2 --as "the new thought"')
    propose(m, a, b, child, "infrastructure", "written by you", "you", today)
    return approve(m, pair_id(a, b), today)


# ---- gaps and a summary -------------------------------------------------------------------------------------
def gaps(m: Map) -> dict:
    """What the map is missing, in plain lists."""
    live, deg = m.live(), m.degree()
    helped = {ln["b"] for ln in m.links if ln["kind"] == HINT}
    helped |= {x for ln in m.links if ln["kind"] in JOINS for x in (ln["a"], ln["b"])}
    by_subject: dict[str, set[str]] = defaultdict(set)
    for t in live.values():
        by_subject[t["subject"]].add(t["source"])
    return {
        "waits_model": [s for s in m.sources.values() if s.get("status") == "waits_model"],
        "waits_reader": [s for s in m.sources.values() if s.get("status") == "waits_reader"],
        "waits_frame": [s for s in m.sources.values() if s.get("status") == "waits_frame"],
        "contradictions": [ln for ln in m.links if ln["kind"] == "contradicts" and ln["a"] in live and ln["b"] in live],
        "needs_alone": [t for t in live.values() if t["role"] == "need" and t["id"] not in helped],
        "alone": [t for t in live.values() if not deg.get(t["id"]) and t["role"] != "need"],
        "thin": sorted(s for s, srcs in by_subject.items()
                       if len(srcs) == 1 and s not in (CARDS_SUBJECT, MARRIED_SUBJECT)),
        "marriages": [r for r in m.marriages.values() if r["state"] == "proposed"],
    }


def summary(m: Map) -> dict:
    live = m.live()
    return {"thoughts": len(live), "left": len(m.thoughts) - len(live),
            "subjects": dict(Counter(t["subject"] for t in live.values()).most_common()),
            "roles": {r: sum(t["role"] == r for t in live.values()) for r in ROLES},
            "links": {k: sum(ln["kind"] == k for ln in m.links) for k in KINDS},
            "sources": dict(Counter(s.get("kind", "?") for s in m.sources.values())),
            "married": sum(r["state"] == "approved" for r in m.marriages.values()),
            "waiting": sum(r["state"] == "proposed" for r in m.marriages.values())}
