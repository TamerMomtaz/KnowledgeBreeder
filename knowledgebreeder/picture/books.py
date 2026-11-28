"""The frame-outer: kb's agent for books. You give it a title; it gives the book back as four things you use.

1. The framework: the book's ideas as a handful of principles, each with what it says and how you would use it.
2. A platform of its own: one platform that would carry out the book's ideas by itself.
3. Features for your platforms: which feature, from which principle, could go into which platform on your cards.
4. A song: the book's philosophy as lyrics you can sing, so the ideas stay with you.

You listen to books (Audible gives no export of clips), so the frame-outer works from the title and from what the
model knows about the book. Everything it writes is marked as the model's reading, not your clips: it says when it
does not know a book, and you tick what rings true in Your ideas. A feature can only name a platform that is one of
your cards; any other name is dropped and counted.

What goes to the model: the title, and the name and first line of each card that is not private. Your private list
and the #private mark hold back the same lines as for advice. One book is one question; its cost goes into the run
log like advice, under the same daily cap on the page.

Files, in work/books/:
    shelf.json      every title you gave, when, and where it stands (waiting, framed, failed)
    SLUG.json       the frame as the model gave it, checked
    SLUG.md         the same as a page, also kept in work/ideas/ so its lines show in Your ideas
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .. import models
from . import ideas
from . import private as _private

MAX_A_RUN = 5                         # books framed by one press; the rest wait for the next
STATES = ("waiting", "framed", "failed")
LANGUAGES = {"en": "English", "ar": "Egyptian Arabic"}

SYSTEM = """You are the frame-outer, one agent of kb, a person's own knowledge assistant. The person listens to a book
and wants it turned into things they build and remember. Work only from what you really know about the book. If you
do not know this book well enough to name its real ideas, say so with "known": false and leave the rest empty: an
invented framework is worse than none.

Reply with one JSON object, no words outside it:
{"known": true or false,
 "author": "the author, as you know it",
 "framework": [ 5 to 9 items: {"name": "short name of a principle", "says": "what the book says, one sentence",
               "use": "how this person could use it in their work, one sentence"} ],
 "platform": {"name": "a name for a platform of its own", "what": "what it does, one sentence",
              "how": [ 3 to 6 short lines: how it carries out the book's ideas ],
              "principles": [ names from the framework it rests on ]},
 "features": [ up to 8 items: {"platform": "EXACTLY one of the platform names listed below",
               "feature": "the feature, one sentence", "principle": "a name from the framework",
               "why": "why it fits that platform, one sentence"} ],
 "song": {"title": "a title", "lyrics": "a short song, verses and a chorus, lines split by \\n"},
 "unsure": "one sentence on what you are least sure of in this book, or empty"}

Write every value in %(language)s, except the platform names, which you copy exactly as listed. In the song, each
verse should carry a principle from the framework, and the chorus the book's one big idea, so singing it brings the
ideas back. Never put a platform in "features" that is not in the list; if none fits, give fewer features."""


def slug(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]
    if not s:                                         # an Arabic title keeps a name made from its letters
        s = "book-" + "".join(f"{ord(c):x}" for c in title.strip()[:12])[:40]
    return s


class Shelf:
    """Your books and where each stands, in work/books/shelf.json."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.path = self.folder / "shelf.json"

    def read(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".part")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, titles: list[str], today: date, via: str = "page") -> list[str]:
        """Put titles on the shelf. A title already there is left as it is. Returns the new ones."""
        data, new = self.read(), []
        for t in titles:
            t = " ".join(str(t).split()).strip()[:200]
            if not t:
                continue
            k = slug(t)
            if k in data:
                continue
            data[k] = {"title": t, "added": today.isoformat(), "via": via, "status": "waiting"}
            new.append(t)
        if new:
            self._write(data)
        return new

    def set(self, key: str, **fields: Any) -> None:
        data = self.read()
        data.setdefault(key, {}).update(fields)
        self._write(data)

    def waiting(self) -> list[tuple[str, dict]]:
        return [(k, v) for k, v in self.read().items() if v.get("status") == "waiting"]

    def items(self) -> list[tuple[str, dict]]:
        """Every book, the newest first."""
        return sorted(self.read().items(), key=lambda kv: (kv[1].get("added") or "", kv[0]), reverse=True)

    def frame(self, key: str) -> dict | None:
        try:
            return json.loads((self.folder / f"{key}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def platforms(cards: dict[str, dict], guard: _private.Private) -> tuple[list[tuple[str, str]], int]:
    """(name, first line) of each card that may leave this laptop, and how many were held back."""
    keep, held = [], 0
    for c in cards.values():
        name, line = c.get("name") or "", c.get("one_line") or ""
        if not name or guard.holds(f"{name} {line}") or _private.marked(f"{name} {line}"):
            held += 1
            continue
        keep.append((name, " ".join(line.split())[:200]))
    return keep, held


MERGE = """You are the frame-outer's judge, one agent of kb. Two models each read the same book for a person and
framed it. Bring the two readings together into one, the best of both: keep what both say; where they differ, keep
the one that is truer to the book and more useful to this person; drop anything that looks made up. Do not add
principles neither reading has, unless one of them plainly missed a principle the book is known for, and then say so
in "differ". If neither reading knows the book, reply with "known": false.

Reply with one JSON object, no words outside it, in the same shape as the readings:
{"known": ..., "author": ..., "framework": [...], "platform": {...}, "features": [...], "song": {...}, "unsure": ...,
 "agree": [ up to 6 short lines: where the two readings agree ],
 "differ": [ up to 6 short lines: where they differ, and which one you kept and why ]}

Write every value in %(language)s. Copy platform names in "features" exactly as listed; never add one that is not
listed. Write one new song that carries the merged framework."""


def merge_prompt(title: str, readings: dict[str, dict], plats: list[tuple[str, str]],
                 lang: str = "en") -> tuple[str, str]:
    system = MERGE % {"language": LANGUAGES.get(lang, "English")}
    listed = "\n".join(f"- {n}: {line}" if line else f"- {n}" for n, line in plats) or "- (none yet)"
    keep = ("known", "author", "framework", "platform", "features", "song", "unsure")
    shown = "\n\n".join(f"Reading {i} (by {who}):\n" + json.dumps({k: f.get(k) for k in keep}, ensure_ascii=False)
                         for i, (who, f) in enumerate(readings.items(), 1))
    return system, f"The book: {title}\n\nThe person's platforms (name: what it is):\n{listed}\n\n{shown}"


def prompt(title: str, plats: list[tuple[str, str]], lang: str = "en") -> tuple[str, str]:
    system = SYSTEM % {"language": LANGUAGES.get(lang, "English")}
    listed = "\n".join(f"- {n}: {line}" if line else f"- {n}" for n, line in plats) or "- (none yet)"
    return system, f"The book: {title}\n\nThe person's platforms (name: what it is):\n{listed}"


def _s(x: Any, n: int = 400) -> str:
    return " ".join(str(x or "").split())[:n]


def check(raw: Any, plats: list[tuple[str, str]]) -> dict:
    """The model's reply, kept to the shape above. Features naming a platform that is not a card are dropped."""
    if not isinstance(raw, dict):
        raise models.ModelError("the frame-outer's answer was not a JSON object.")
    known = raw.get("known") is not False
    fw = [{"name": _s(p.get("name"), 80), "says": _s(p.get("says")), "use": _s(p.get("use"))}
          for p in (raw.get("framework") or []) if isinstance(p, dict) and _s(p.get("name"))][:9]
    pl = raw.get("platform") if isinstance(raw.get("platform"), dict) else {}
    platform = {"name": _s(pl.get("name"), 80), "what": _s(pl.get("what")),
                "how": [_s(x, 200) for x in (pl.get("how") or []) if _s(x)][:6],
                "principles": [_s(x, 80) for x in (pl.get("principles") or []) if _s(x)][:9]}
    names = {n.lower(): n for n, _ in plats}
    feats, dropped = [], 0
    for f in raw.get("features") or []:
        if not isinstance(f, dict) or not _s(f.get("feature")):
            continue
        real = names.get(_s(f.get("platform"), 120).lower())
        if not real:
            dropped += 1
            continue
        feats.append({"platform": real, "feature": _s(f.get("feature")), "principle": _s(f.get("principle"), 80),
                      "why": _s(f.get("why"))})
    so = raw.get("song") if isinstance(raw.get("song"), dict) else {}
    lyrics = "\n".join(ln.rstrip() for ln in str(so.get("lyrics") or "").replace("\\n", "\n").splitlines())[:4000]
    out = {"known": known and bool(fw), "author": _s(raw.get("author"), 120), "framework": fw, "platform": platform,
           "features": feats[:8], "dropped_features": dropped,
           "song": {"title": _s(so.get("title"), 120), "lyrics": lyrics.strip()}, "unsure": _s(raw.get("unsure"))}
    if not out["known"]:
        out.update(framework=[], platform={"name": "", "what": "", "how": [], "principles": []}, features=[],
                   song={"title": "", "lyrics": ""})
    return out


def merge_one(title: str, readings: dict[str, dict], judge: models.Model, plats: list[tuple[str, str]],
              lang: str = "en", allow=()) -> tuple[dict, models.Answer]:
    """The judge brings two (or more) readings together. The result is checked like any reading."""
    system, user = merge_prompt(title, readings, plats, lang)
    raw, answer = models.ask_json(judge, system, user, allow=allow,
                                  sending=f"the title of one book, {len(readings)} models' readings of it, and the "
                                          f"name and first line of {len(plats)} cards")
    f = check(raw, plats)
    f["agree"] = [_s(x, 240) for x in (raw.get("agree") or [] if isinstance(raw, dict) else []) if _s(x)][:6]
    f["differ"] = [_s(x, 240) for x in (raw.get("differ") or [] if isinstance(raw, dict) else []) if _s(x)][:6]
    return f, answer


def md(title: str, f: dict, worker: str, day: str) -> str:
    """The frame as a page. Its headings are the ones Your ideas reads: principles, platform idea, feature ideas."""
    by = f" by {f['author']}" if f.get("author") else ""
    L = [f"# BOOK: {title}", "", f"framed: {day}, by the frame-outer with {worker}{by}",
         "what this is: the model's reading of the book from what it knows, not your clips. Tick what rings true.", ""]
    if not f["known"]:
        L += ["The model said it does not know this book well enough to frame it, so nothing was made up.", ""]
        return "\n".join(L)
    L += ["## The book's principles (its framework)", ""]
    L += [f"{i}. **{p['name']}.** {p['says']} Use: {p['use']}" for i, p in enumerate(f["framework"], 1)]
    pl = f["platform"]
    if pl.get("name"):
        L += ["", "## A platform idea of its own", "",
              f"- **{pl['name']}.** {pl['what']}" + (f" Rests on: {', '.join(pl['principles'])}." if pl["principles"]
                                                     else "")]
        L += [f"    - {h}" for h in pl["how"]]
    if f["features"]:
        L += ["", "## Feature ideas for your platforms", ""]
        L += [f"- **{x['platform']}: {x['feature']}** From \"{x['principle']}\". {x['why']}" for x in f["features"]]
    if f["song"]["lyrics"]:
        L += ["", f"## The song: {f['song']['title'] or title}", ""] + [f"    {ln}" for ln in f["song"]["lyrics"].splitlines()]
    if f.get("unsure"):
        L += ["", "## Reality check", "", f"- The model is least sure of this: {f['unsure']}"]
    if f.get("agree") or f.get("differ"):
        L += ["", "## How the readings compare", ""] + [f"- Both say: {x}" for x in f.get("agree") or []]
        L += [f"- They differ: {x}" for x in f.get("differ") or []]
    return "\n".join(L) + "\n"


def frame_one(title: str, m: models.Model, plats: list[tuple[str, str]], lang: str = "en",
              allow: tuple[str, ...] | list[str] = ()) -> tuple[dict, models.Answer]:
    system, user = prompt(title, plats, lang)
    raw, answer = models.ask_json(m, system, user, allow=allow,
                                  sending=f"the title of one book and the name and first line of {len(plats)} cards")
    return check(raw, plats), answer


def who_framed(names: list[str], judge: str | None) -> str:
    """How the shelf names who framed a book: one model, two side by side, or two brought together by a third."""
    both = " + ".join(names)
    return f"{both} → {judge}" if judge and len(names) > 1 else both


def frame_waiting(shelf: Shelf, ideas_dir: str | Path, cards: dict[str, dict], m: models.Model,
                  guard: _private.Private, today: date, lang: str = "en", allow=(), log=None,
                  only: list[str] | None = None, limit: int = MAX_A_RUN, also: list[models.Model] | tuple = (),
                  judge: models.Model | None = None) -> dict:
    """Frame the books that wait (or the ones named), up to limit. Each result is on the shelf and in Your ideas.
    With also, more models read each book too; with a judge, the judge brings their readings together into one."""
    plats, held = platforms(cards, guard)
    todo = [(k, v) for k, v in shelf.waiting() if not only or v["title"] in only][:limit]
    readers = [m, *[x for x in also if x.name != m.name]]
    judge = judge if judge is not None and len(readers) > 1 else None
    label = who_framed([x.name for x in readers], judge.name if judge else None)
    run = log.start("frame", label=label, subject=f"{len(todo)} books") if log else None
    done: list[dict] = []
    for key, entry in todo:
        title = entry["title"]
        readings: dict[str, dict] = {}
        costs, errors, model_ids = 0.0, [], []
        for r in readers:
            try:
                f1, a1 = frame_one(title, r, plats, lang, allow)
            except (models.ModelError, models.Refused) as e:
                errors.append(f"{r.name}: {str(e)[:200]}")
                if run:
                    run.record("frame", worker=r.name, subject=title, status="failed", error=str(e)[:300])
                continue
            f1.update(worker=r.name, model=a1.model, cost=a1.cost)
            readings[r.name] = f1
            costs += a1.cost or 0.0
            model_ids.append(a1.model)
            if run:
                run.record("frame", worker=r.name, subject=title, tokens_in=a1.tokens_in, tokens_out=a1.tokens_out,
                           cost=a1.cost, duration_ms=a1.ms, where=a1.where, known=f1["known"])
        if not readings:
            err = "; ".join(errors)[:300]
            shelf.set(key, status="failed", error=err, tried=today.isoformat(), worker=label)
            done.append({"title": title, "status": "failed", "error": err})
            continue
        known = {k: v for k, v in readings.items() if v["known"]}
        f, by = next(iter(known.values() or readings.values())), next(iter(known or readings))
        if judge and len(known) > 1:
            try:
                f, aj = merge_one(title, known, judge, plats, lang, allow)
                costs += aj.cost or 0.0
                by = who_framed(list(known), judge.name)
                if run:
                    run.record("frame-merge", worker=judge.name, subject=title, tokens_in=aj.tokens_in,
                               tokens_out=aj.tokens_out, cost=aj.cost, duration_ms=aj.ms, where=aj.where)
            except (models.ModelError, models.Refused) as e:
                errors.append(f"{judge.name} could not bring them together: {str(e)[:200]}")
        f = dict(f)
        f.update(title=title, worker=by, model=", ".join(x for x in model_ids if x), framed=today.isoformat(),
                 cost=round(costs, 6), at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if len(readings) > 1:
            f["readings"] = readings
        if errors:
            f["errors"] = errors
        shelf.folder.mkdir(parents=True, exist_ok=True)
        (shelf.folder / f"{key}.json").write_text(json.dumps(f, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        page = md(title, f, by, today.isoformat())
        (shelf.folder / f"{key}.md").write_text(page, encoding="utf-8")
        kept = ideas.keep_file(ideas_dir, f"book-{key}.md", page)
        shelf.set(key, status="framed", framed=today.isoformat(), worker=by, known=f["known"],
                  ideas=kept["rows"], error=None)
        done.append({"title": title, "status": "framed", "known": f["known"], "ideas": kept["rows"],
                     "features": len(f["features"]), "dropped": f["dropped_features"], "cost": round(costs, 6),
                     "by": by, **({"errors": errors} if errors else {})})
    if run:
        run.end("ok" if any(d["status"] == "framed" for d in done) or not done else "failed")
    return {"run": run.id if run else None, "worker": label, "books": done, "held_cards": held,
            "left": len(shelf.waiting())}
