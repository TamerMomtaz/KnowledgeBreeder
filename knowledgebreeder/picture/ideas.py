"""Your ideas: one ledger of every idea, lesson, check and book principle kb has read, each with where it came from.

This is the base the next parts stand on (the bookshelf, the forgot-checker, the matcher). It reads two places:

- your cards: the ideas not started and the reusable parts on each card;
- the files in work/ideas/: journey files, "KB thinks" files and any markdown like them. Under a heading about
  lessons, strengths, weak spots, what you forgot, ideas or books, each list line (or bold paragraph) is one row.
  Timelines, sources and how-it-works sections are story, not ideas, and are left out.

Nothing is stored but what you said and when kb first saw a row: the rows are worked out from their sources each
time, so a row never goes stale. "Computed, never stored" is the same rule your other platforms keep.
You answer each row: useful, not now, or done. Two numbers say whether this is working: of the rows you answered
in the last 7 days, how many were useful; and how many you marked done in the last 30 days. No model reads anything here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

STATES = ("useful", "later", "done")
# the order rows come in when kb picks what to show you: what you may have forgotten first
KINDS = ("check", "lesson", "idea", "principle", "weak", "part", "strength")
MAX_FILE = 2_000_000

# a heading's words decide what its lines are; the first rule that matches wins
_RULES = (
    (re.compile(r"timeline|sources?\b|in one minute|how it works|how it was built|reverse|what kb needs|stack|"
                r"rejected|watch list|run cost|build order|song|lyrics", re.I), None),
    (re.compile(r"lesson|moral", re.I), "lesson"),
    (re.compile(r"forgot|keep an eye|checks?\b|reality", re.I), "check"),
    (re.compile(r"weak", re.I), "weak"),
    (re.compile(r"strength", re.I), "strength"),
    (re.compile(r"book|resonat|principle|highlight", re.I), "principle"),
    (re.compile(r"idea|together|shares|match|angle|picks?\b|multiplier|features?\b", re.I), "idea"),
)
_ITEM = re.compile(r"^\s{0,3}(?:[-*]|\d{1,2}[.)])\s+(.*)$")
_BOLD_PARA = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")
_MD = re.compile(r"\*\*|__|`|\[([^\]]*)\]\([^)]*\)")


def kind_of(heading: str) -> str | None:
    for rx, kind in _RULES:
        if rx.search(heading or ""):
            return kind
    return None


def _clean(s: str) -> str:
    s = _MD.sub(lambda m: m.group(1) or "", s)
    return " ".join(s.split())


def _id(source: str, kind: str, text: str) -> str:
    """The same line about the same project keeps its id, so a file sent again, or a newer copy, stays answered."""
    return hashlib.sha1(f"{source}|{kind}|{text.lower()}".encode()).hexdigest()[:12]


def project_of(text: str, fallback: str) -> str:
    """The project a file is about: its card: line, or its title after a colon."""
    for line in text.splitlines()[:12]:
        m = re.match(r"card:\s*(.+?)(?:\s*\(|,|$)", line.strip(), re.I)
        if m:
            return m.group(1).strip()
    for line in text.splitlines()[:3]:
        m = re.match(r"#\s+[^:]+:\s*(.+)$", line.strip())
        if m:
            return _clean(re.sub(r",\s*at the depth.*$", "", m.group(1)))
    return fallback


def parse(text: str, name: str) -> list[dict]:
    """The rows in one markdown file. Each: id, kind, project, text, source (file, line and heading)."""
    project = project_of(text, Path(name).stem)
    rows: list[dict] = []
    h2 = h3 = ""
    kind: str | None = None
    parent = ""                       # a bold paragraph's title, so the lines under it read on their own
    fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), _clean(m.group(2))
            if level <= 2:
                h2, h3 = title, ""
                kind = kind_of(title)
            else:
                h3 = title
                kind = kind_of(title) or kind_of(h2)
            parent = ""
            continue
        if not kind:
            continue
        body = None
        im = _ITEM.match(line)
        if im:
            body = f"{parent}: {im.group(1)}" if parent and line.lstrip().startswith("-") else im.group(1)
        else:
            bm = _BOLD_PARA.match(line.strip())
            if bm:
                body = f"{bm.group(1)} {bm.group(2)}"
                parent = _clean(bm.group(1)).rstrip(".:")
        if body is None:
            continue
        t = _clean(body)
        if len(t) < 12:
            continue
        if len(t) > 500:
            t = t[:497].rstrip() + "..."
        where = f"{Path(name).name}:{n}" + (f" · {h3 or h2}" if (h3 or h2) else "")
        rows.append({"id": _id(project, kind, t), "kind": kind, "project": project, "text": t,
                     "source": where})
    return rows


def from_cards(cards: dict) -> list[dict]:
    """The ideas not started and the reusable parts on your cards."""
    rows = []
    for c in cards.values():
        for kind, field in (("idea", "ideas"), ("part", "parts")):
            for item in c.get(field) or []:
                p = [str(x) for x in item if x] if isinstance(item, list) else [str(item)] if item else []
                if not p:
                    continue
                t = _clean(" · ".join(p))
                if len(t) < 6:
                    continue
                name = c.get("name") or c["id"]
                rows.append({"id": _id("card:" + c["id"], kind, t), "kind": kind, "project": name, "text": t,
                             "source": f"card {name}"})
    return rows


def read_folder(folder: str | Path) -> list[dict]:
    rows: list[dict] = []
    folder = Path(folder)
    if not folder.is_dir():
        return rows
    for p in sorted(folder.glob("*.md")):
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            rows += parse(p.read_text(encoding="utf-8", errors="replace"), p.name)
        except OSError:
            continue
    return rows


def ledger(cards: dict | None, folder: str | Path) -> list[dict]:
    """Every row, each once, in KINDS order."""
    seen, out = set(), []
    for r in read_folder(folder) + from_cards(cards or {}):
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return sorted(out, key=lambda r: KINDS.index(r["kind"]))


def keep_file(folder: str | Path, name: str, text: str) -> dict:
    """Keep one ideas file in work/ideas/, never overwriting an earlier one. Says how many rows it holds."""
    if len(text) > MAX_FILE:
        raise KeyError("that file is too big.")
    text = text.lstrip("﻿")
    rows = parse(text, name)
    if not rows:
        return {"rows": 0, "name": name}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "-", Path(name).stem).strip("-") or "ideas"
    keep = folder / f"{stem}.md"
    n = 2
    while keep.exists() and keep.read_text(encoding="utf-8", errors="replace") != text:
        keep = folder / f"{stem}~{n}.md"
        n += 1
    if not keep.exists():
        tmp = keep.with_suffix(".part")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, keep)
    return {"rows": len(rows), "name": name, "kept": str(keep)}


class Book:
    """Your answers and when kb first saw each row, in one small file (work/ideas.json)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict:
        try:
            got = json.loads(self.path.read_text(encoding="utf-8"))
            return got if isinstance(got, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".part")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def marks(self) -> dict[str, dict]:
        m = self._read().get("marks") or {}
        return {k: v for k, v in m.items() if isinstance(v, dict) and v.get("state") in STATES}

    def first_seen(self, rows: list[dict], today: date) -> dict[str, str]:
        """When kb first saw each row; rows seen for the first time get today."""
        data = self._read()
        seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
        new = {r["id"]: today.isoformat() for r in rows if r["id"] not in seen}
        if new:
            seen.update(new)
            data["seen"] = seen
            self._write(data)
        return seen

    def mark(self, row_id: str, state: str, today: date) -> dict:
        if not re.fullmatch(r"[0-9a-f]{12}", row_id or ""):
            raise KeyError("no such row.")
        if state not in (*STATES, ""):
            raise KeyError("state must be useful, later, done or empty.")
        data = self._read()
        marks = self.marks()
        if state:
            marks[row_id] = {"state": state, "at": today.isoformat()}
        else:
            marks.pop(row_id, None)
        data["marks"] = marks
        self._write(data)
        return marks


def numbers(marks: dict[str, dict], today: date) -> dict:
    """The two numbers that say whether kb's ideas help: the useful share of last week's answers, and done this month."""
    week, month = today - timedelta(days=7), today - timedelta(days=30)

    def after(m, d):
        try:
            return date.fromisoformat(m.get("at", "")) > d
        except ValueError:
            return False

    answered = [m for m in marks.values() if after(m, week)]
    useful = sum(1 for m in answered if m["state"] in ("useful", "done"))
    done = sum(1 for m in marks.values() if m["state"] == "done" and after(m, month))
    return {"answered_7d": len(answered), "useful_7d": useful,
            "useful_share": round(useful / len(answered), 2) if answered else None, "done_30d": done}


def view(rows: list[dict], book: Book, today: date, show: int = 7) -> dict:
    """What the page and kb picture ideas show: counts, the rows to answer (oldest first, what you may have forgotten
    first), the useful ones, and the two numbers."""
    seen = book.first_seen(rows, today)
    marks = book.marks()
    for r in rows:
        r["seen"] = seen.get(r["id"], today.isoformat())
        r["state"] = (marks.get(r["id"]) or {}).get("state", "new")
    count = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    new = sorted((r for r in rows if r["state"] == "new"), key=lambda r: (r["seen"], KINDS.index(r["kind"])))
    # take turns across projects, so one big file does not fill the list
    by_project: dict[str, list[dict]] = {}
    for r in new:
        by_project.setdefault(r["project"], []).append(r)
    turns, i = [], 0
    while len(turns) < len(new):
        for rs in by_project.values():
            if i < len(rs):
                turns.append(rs[i])
        i += 1
    return {"rows": len(rows), "count": count, "projects": len(by_project) or len({r["project"] for r in rows}),
            "to_answer": turns[:show], "new": len(new),
            "useful": [r for r in rows if r["state"] == "useful"],
            "later": sum(1 for r in rows if r["state"] == "later"),
            "done": sum(1 for r in rows if r["state"] == "done"),
            "numbers": numbers(marks, today)}


def md(v: dict) -> str:
    """kb picture ideas, as text."""
    out = [f"Your ideas: {v['rows']} rows. "
           + ", ".join(f"{n} {k}" for k, n in v["count"].items() if n) + "."]
    nb = v["numbers"]
    if nb["answered_7d"]:
        out.append(f"Last 7 days: {nb['useful_7d']} of {nb['answered_7d']} answered were useful. "
                   f"Done in 30 days: {nb['done_30d']}.")
    else:
        out.append("Nothing answered in the last 7 days yet.")
    if v["to_answer"]:
        out.append("\nTo answer (oldest first):")
        for r in v["to_answer"]:
            out.append(f"  {r['id']}  [{r['kind']} · {r['project']}] {r['text']}\n      from {r['source']}")
    if v["useful"]:
        out.append(f"\nUseful ({len(v['useful'])}):")
        for r in v["useful"]:
            out.append(f"  {r['id']}  [{r['kind']} · {r['project']}] {r['text']}")
    if v["to_answer"]:
        out.append(f"\nAnswer one, for example: kb picture ideas --mark {v['to_answer'][0]['id']} useful"
                   " (or later, or done).")
    return "\n".join(out) + "\n"
