"""The page's buttons for the jobs that used to need a terminal: ask for advice, find chances in the inbox, add cards.

Advice and the scout run the very command you would type (``kb picture advise``, ``kb scout read``), as a separate
process on this laptop, so every rule stays the same: your private list, your lessons, the run log, the scout's
ledger, and the gate. One job runs at a time; the page asks how it is going and shows the result as one plain sentence.

Advice asks every model you like (you said so on 25 Nov 2026): the models on this laptop, and each paid model whose
key kb keeps (``kb keys add NAME``) and whose price it knows, up to your daily cap (``daily_cap`` in the models file,
$1 until you say another). The page passes ``--allow`` for those paid models only. Before it starts, kb adds what the
paid models cost today in the run log to what this run would likely cost (the most one advice run from that model has
cost so far, or the most it could cost before its first run) and leaves out each paid model that would go over the
cap. Private lines are cut before anything goes to a model off this laptop, as on the command line. The scout reads
your whole inbox, one ask per item, so it stays on this laptop's models.

Adding cards goes through the same merge as ``kb picture add``: nothing is overwritten, an older version of a card
is kept in its history, and a copy of the file you chose is kept in work/cards, so kb can always say where a card
came from.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock
from pathlib import Path

from .. import keys, models
from ..models.client import HERE
from ..models.config import CAP

PKG_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 3 * 3600                   # a long advice run on a laptop takes minutes; three hours means it is stuck
MAX_CARDS = 2_000_000                # a cards file; your biggest is under 50 KB
Runner = Callable[[list[str]], tuple[int, str, str]]


class Busy(Exception):
    """A job is running already."""


def spent(runlog: str | Path, day: date) -> float:
    """Dollars the models off this laptop cost on this day (the laptop's own day), from the run log."""
    if not Path(runlog).exists():
        return 0.0
    start = datetime.combine(day, clock.min).astimezone()
    lo, hi = (x.astimezone(timezone.utc).isoformat(timespec="milliseconds") for x in (start, start + timedelta(days=1)))
    try:
        db = sqlite3.connect(f"file:{Path(runlog).resolve()}?mode=ro", uri=True, timeout=5)
        try:
            rows = db.execute("SELECT cost, meta FROM steps WHERE started >= ? AND started < ? AND cost > 0",
                              (lo, hi)).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return 0.0
    total = 0.0
    for cost, meta in rows:
        try:
            where = (json.loads(meta) or {}).get("where") if meta else None
        except (ValueError, AttributeError):
            where = None
        if where != HERE:                           # a local model with a price set is not money spent
            total += cost
    return round(total, 6)


def likely(m: models.Model, runlog: str | Path) -> float:
    """What one advice run from this paid model will likely cost: the most one has cost so far, or before its first
    run, the most it could (its whole evidence budget at about three characters a token, a full answer, asked twice
    when the first answer is not JSON)."""
    most = None
    if Path(runlog).exists():
        try:
            db = sqlite3.connect(f"file:{Path(runlog).resolve()}?mode=ro", uri=True, timeout=5)
            try:
                most = db.execute("SELECT MAX(cost) FROM steps WHERE name = 'advise' AND worker = ? AND cost > 0",
                                  (m.name,)).fetchone()[0]
            finally:
                db.close()
        except sqlite3.Error:
            most = None
    if most:
        return float(most)
    return round(2 * (m.budget / 3 * (m.price_in or 0) + m.max_tokens * (m.price_out or 0)) / 1_000_000, 4)


def choose(models_file: str | Path, runlog: str | Path, day: date, keys_file: str | Path | None = None) -> dict:
    """Which models the page asks, and why each other one is left out.

    here: the models on this laptop (or on your network marked lan), the file's default first. paid: the models off
    this laptop that have a kept key and a known price and fit under today's cap. out: (name, why) for the rest.
    """
    try:
        book = models.load(models_file)
    except KeyError as e:
        return {"here": [], "paid": [], "out": [], "spent": 0.0, "cap": CAP, "problem": str(e.args[0])}
    kept = keys.load(keys_file)
    order = sorted(book.models.values(), key=lambda m: m.name != book.default)
    here = [m.name for m in order if models.allowed(m)]
    paid: list[str] = []
    out: list[tuple[str, str]] = []
    total = spent(runlog, day)
    room = book.cap - total
    for m in order:
        if m.name in here:
            continue
        if not m.key_env:
            out.append((m.name, "no_key_env"))
        elif not (kept.get(m.key_env) or os.environ.get(m.key_env)):
            out.append((m.name, "no_key"))
        elif m.price_in is None or m.price_out is None:
            out.append((m.name, "no_price"))
        elif m.protocol == "anthropic" and importlib.util.find_spec("anthropic") is None:
            out.append((m.name, "no_sdk"))
        elif book.cap <= 0:
            out.append((m.name, "cap_zero"))
        elif likely(m, runlog) > room:
            out.append((m.name, "over_cap"))
        else:
            paid.append(m.name)
            room -= likely(m, runlog)
    problem = None if here or paid else (f"{models_file} names no model yet." if not book.models else
                                         "no model in it can be asked now.")
    return {"here": here, "paid": paid, "out": out, "spent": total, "cap": book.cap, "problem": problem}


def cli(*args) -> list[str]:
    return [sys.executable, "-m", "knowledgebreeder.cli", *(str(a) for a in args)]


def advise_argv(kb, names: list[str], lang: str = "en", allow: list[str] | None = None) -> list[str]:
    """The advice command. ``allow`` names the paid models the page chose under your cap; nothing else is allowed."""
    day = ["--today", kb.today.isoformat()] if kb.today else []
    let = ["--allow", ",".join(allow)] if allow else []
    return cli("picture", "--file", kb.picture, "advise", "--models", ",".join(names), "--models-file", kb.models,
               "--runlog", kb.runlog, "--lessons", kb.lessons, "--private", kb.private, "--lang", lang, "--json",
               *let, *day)


def scout_argv(kb, name: str) -> list[str]:
    day = ["--today", kb.today.isoformat()] if kb.today else []
    return cli("scout", "--file", kb.picture, "--ledger", kb.ledger, "read", kb.inbox.root / "text", "--model", name,
               "--models-file", kb.models, "--runlog", kb.runlog, "--private", kb.private, "--json", *day)


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    env = keys.env(os.environ)                    # read again for every job: a key you just added works now
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(PKG_ROOT), env.get("PYTHONPATH", "")) if x)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT, env=env,
                           check=False)
    except subprocess.TimeoutExpired:
        return 124, "", "it ran for three hours without finishing, so kb stopped it"
    except OSError as e:
        return 127, "", f"kb could not start it: {e.strerror or e}"
    return r.returncode, r.stdout, r.stderr


def why(err: str, code: int) -> str:
    """The reason a job failed, as the command said it, in one line."""
    if code == 3:
        return "a model off this laptop would have been asked without being allowed, so nothing was sent"
    lines = [x.strip() for x in (err or "").splitlines() if x.strip()]
    said = lines[-1] if lines else f"it stopped with code {code}"
    return said.removeprefix("error: ")[:400]


class Jobs:
    """One job at a time, run in the background. ``state()`` is what the page shows."""

    def __init__(self, runner: Runner | None = None):
        self.lock = threading.Lock()
        self.now: dict | None = None
        self.runner = runner or run_cli
        self._thread: threading.Thread | None = None

    def state(self) -> dict:
        with self.lock:
            return dict(self.now) if self.now else {"status": "idle"}

    def start(self, kind: str, argv: list[str], **meta) -> dict:
        with self.lock:
            if self.now and self.now["status"] == "running":
                raise Busy(self.now["kind"])
            job = {"kind": kind, "status": "running", "started": time.time(), **meta}
            self.now = job
            started = dict(job)                       # as it started, even when the job ends before this returns
        self._thread = threading.Thread(target=self._go, args=(job, argv), daemon=True)
        self._thread.start()
        return started

    def _go(self, job: dict, argv: list[str]) -> None:
        try:
            code, out, err = self.runner(argv)
        except Exception as e:                                # noqa: BLE001 - a job must always end
            code, out, err = 1, "", f"{type(e).__name__}: {e}"
        result = None
        if out.strip():
            try:
                result = json.loads(out)
            except ValueError:
                result = None
        with self.lock:
            job["ended"] = time.time()
            if isinstance(result, dict) and (code == 0 or "results" in result):
                job.update(status="done", result=result)      # advice exits 2 when every model failed, with the reasons
            else:
                job.update(status="failed", error=why(err, code))

    def wait(self, timeout: float = 30) -> dict:
        t = self._thread
        if t:
            t.join(timeout)
        return self.state()


def advice_summary(result: dict) -> dict:
    rs = result.get("results") or []
    return {"run": result.get("run"), "ok": [r["worker"] for r in rs if r.get("advice")],
            "failed": [{"worker": r["worker"], "error": r.get("error", "")} for r in rs if "error" in r]}


def scout_summary(result: dict) -> dict:
    rows = result.get("rows") or []
    fresh = [r for r in rows if not r.get("seen_before")]
    return {"read": len(fresh), "before": len(rows) - len(fresh),
            "chances": sum(r.get("verdict") == "opportunity" for r in fresh),
            "unsure": sum(r.get("verdict") == "unchecked" for r in fresh),
            "errors": sum(r.get("verdict") == "error" for r in fresh)}


_UNSAFE = re.compile(r"[^0-9A-Za-z؀-ۿ._-]+")


def _keep_name(name: str, day: date) -> str:
    stem = _UNSAFE.sub("-", Path(name or "cards").name).strip(".-")[:80] or "cards"
    if not stem.lower().endswith((".md", ".txt")):
        stem += ".md"
    return f"{day.isoformat()}-{stem}"


def add_cards(picture_path: str | Path, cards_dir: str | Path, name: str, text: str, day: date) -> dict:
    """Merge the PROJECT CARDs in one file into the picture, as ``kb picture add`` does, and keep a copy of the file."""
    from . import Picture, cards, changes
    if len(text) > MAX_CARDS:
        raise KeyError("that file is too big to be a cards file.")
    text = text.lstrip("﻿")
    if not text.strip():
        raise KeyError("that file is empty.")
    folder = Path(cards_dir)
    keep = folder / _keep_name(name, day)
    found = cards.parse(text, origin=str(keep))
    if not found:
        return {"found": 0, "added": [], "updated": [], "unchanged": [], "changed": {}, "name": name}
    raw = text.encode("utf-8")
    folder.mkdir(parents=True, exist_ok=True)
    n = 2
    while keep.exists() and keep.read_bytes() != raw:          # never overwrite an earlier copy
        keep = folder / f"{keep.stem.rsplit('~', 1)[0]}~{n}{keep.suffix}"
        n += 1
    if not keep.exists():
        tmp = keep.with_suffix(keep.suffix + ".part")
        tmp.write_bytes(raw)
        os.replace(tmp, keep)
        found = cards.parse(text, origin=str(keep))
    pic = Picture.load(picture_path) if os.path.exists(picture_path) else Picture()
    res = pic.add(found, recorded=day.isoformat(), fingerprint=changes.fingerprint(raw))
    changed = {}
    for c in found:
        if c["name"] in res["updated"]:
            vs = changes.versions(pic, c["id"])
            changed[c["name"]] = changes.line(changes.diff(vs[-2], vs[-1]))
    pic.save(picture_path)
    return {"found": len(found), "added": res["added"], "updated": res["updated"], "unchanged": res["unchanged"],
            "changed": changed, "cards": len(pic.cards), "kept": str(keep), "name": name}


def md_html(md: str, esc: Callable[[str], str]) -> str:
    """The small markdown kb prints (headings, numbered and dashed lists, indented lines under an item, paragraphs)
    as HTML, every word escaped. Each ## heading opens its own box."""
    out: list[str] = []
    lst: str | None = None
    item_open = False

    def close_list():
        nonlocal lst, item_open
        if item_open:
            out.append("</li>")
            item_open = False
        if lst:
            out.append(f"</{lst}>")
            lst = None

    box_open = False
    for line in md.splitlines():
        if not line.strip():
            continue
        m_num = re.match(r"^(\d+)\.\s+(.*)$", line)
        if line.startswith("## "):
            close_list()
            if box_open:
                out.append("</section>")
            out.append(f'<section class="box"><h2>{esc(line[3:])}</h2>')
            box_open = True
        elif line.startswith("# "):
            continue                                          # the page's own title says it
        elif m_num:
            if lst != "ol":
                close_list()
                out.append('<ol class="md">')
                lst = "ol"
            elif item_open:
                out.append("</li>")
            out.append(f'<li value="{int(m_num.group(1))}"><bdi>{esc(m_num.group(2))}</bdi>')
            item_open = True
        elif line.startswith("- "):
            if lst != "ul":
                close_list()
                out.append('<ul class="md">')
                lst = "ul"
            elif item_open:
                out.append("</li>")
            out.append(f"<li><bdi>{esc(line[2:])}</bdi>")
            item_open = True
        elif line.startswith("   ") and item_open:
            out.append(f'<span class="more"><bdi>{esc(line.strip())}</bdi></span>')
        else:
            close_list()
            if not box_open:
                out.append('<section class="box">')
                box_open = True
            out.append(f"<p><bdi>{esc(line.strip())}</bdi></p>")
    close_list()
    if box_open:
        out.append("</section>")
    return "".join(out)
