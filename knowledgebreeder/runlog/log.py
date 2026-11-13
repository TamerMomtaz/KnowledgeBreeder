"""Writing the run log."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1
MAX_PAYLOAD = 256_000  # characters of JSON kept per input or output; larger ones keep a hash and a preview

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, task TEXT NOT NULL, label TEXT, subject TEXT,
    started TEXT NOT NULL, ended TEXT, status TEXT NOT NULL DEFAULT 'running', error TEXT, meta TEXT);
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), parent_id TEXT REFERENCES steps(id),
    name TEXT NOT NULL, worker TEXT, version TEXT, subject TEXT,
    started TEXT NOT NULL, ended TEXT, duration_ms REAL, status TEXT NOT NULL DEFAULT 'running', error TEXT,
    input TEXT, output TEXT, tokens_in INTEGER, tokens_out INTEGER, cost REAL, meta TEXT);
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id), step_id TEXT REFERENCES steps(id),
    name TEXT NOT NULL, value REAL NOT NULL, note TEXT, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS steps_run ON steps(run_id);
CREATE INDEX IF NOT EXISTS steps_worker ON steps(worker, version);
CREATE INDEX IF NOT EXISTS scores_run ON scores(run_id, name);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def pack(value: Any) -> str | None:
    """JSON for storage. Anything too large is replaced by its hash, size and a preview."""
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_PAYLOAD:
        return text
    return json.dumps({"_truncated": True, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "chars": len(text), "preview": text[:2000]})


class RunLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ runs
    def start(self, task: str, label: str | None = None, subject: str | None = None, **meta: Any) -> "Run":
        rid = _new_id("run")
        self.db.execute("INSERT INTO runs (id, task, label, subject, started, meta) VALUES (?,?,?,?,?,?)",
                        (rid, task, label, subject, _now(), pack(meta or None)))
        return Run(self, rid)

    def get(self, run_id: str) -> "Run":
        """Reattach to a run, so separate processes can add steps to it. A unique prefix of the id is enough."""
        rows = self.db.execute("SELECT id FROM runs WHERE id = ? OR id LIKE ?", (run_id, run_id + "%")).fetchall()
        if len(rows) != 1:
            raise KeyError(f"no single run matches '{run_id}' ({len(rows)} found)")
        return Run(self, rows[0]["id"])

    @contextmanager
    def run(self, task: str, label: str | None = None, subject: str | None = None, **meta: Any) -> Iterator["Run"]:
        r = self.start(task, label, subject, **meta)
        try:
            yield r
        except BaseException as e:
            r.end("failed", error=f"{type(e).__name__}: {e}")
            raise
        else:
            r.end("ok")


class Run:
    def __init__(self, log: RunLog, run_id: str):
        self.log, self.id = log, run_id

    def end(self, status: str = "ok", error: str | None = None) -> None:
        self.log.db.execute("UPDATE runs SET ended = ?, status = ?, error = ? WHERE id = ?",
                            (_now(), status, error, self.id))

    def score(self, name: str, value: float, note: str | None = None) -> None:
        self.log.db.execute("INSERT INTO scores (run_id, step_id, name, value, note, at) VALUES (?,NULL,?,?,?,?)",
                            (self.id, name, float(value), note, _now()))

    def record(self, name: str, *, worker: str | None = None, version: str | None = None, subject: str | None = None,
               input: Any = None, output: Any = None, duration_ms: float | None = None, status: str = "ok",
               error: str | None = None, tokens_in: int | None = None, tokens_out: int | None = None,
               cost: float | None = None, scores: dict[str, float] | None = None, parent: str | None = None,
               **meta: Any) -> str:
        """Write a finished step in one call: for work done elsewhere (a model call, a person, another tool)."""
        sid, now = _new_id("step"), _now()
        self.log.db.execute(
            "INSERT INTO steps (id, run_id, parent_id, name, worker, version, subject, started, ended, duration_ms,"
            " status, error, input, output, tokens_in, tokens_out, cost, meta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, self.id, parent, name, worker, version, subject, now, now, duration_ms, status, error,
             pack(input), pack(output), tokens_in, tokens_out, cost, pack(meta or None)))
        for k, v in (scores or {}).items():
            self.log.db.execute("INSERT INTO scores (run_id, step_id, name, value, at) VALUES (?,?,?,?,?)",
                                (self.id, sid, k, float(v), now))
        return sid

    @contextmanager
    def step(self, name: str, *, worker: str | None = None, version: str | None = None, subject: str | None = None,
             input: Any = None, parent: "Step | None" = None, **meta: Any) -> Iterator["Step"]:
        """Time a piece of work. An exception is recorded on the step and then raised again."""
        sid = _new_id("step")
        self.log.db.execute(
            "INSERT INTO steps (id, run_id, parent_id, name, worker, version, subject, started, input, meta)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, self.id, parent.id if parent else None, name, worker, version, subject, _now(), pack(input),
             pack(meta or None)))
        s = Step(self, sid)
        t0 = time.perf_counter()
        status, error = "ok", None
        try:
            yield s
        except BaseException as e:
            status = "failed"
            error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=5)}"
            raise
        finally:
            self.log.db.execute(
                "UPDATE steps SET ended = ?, duration_ms = ?, status = ?, error = ?, output = ?, tokens_in = ?,"
                " tokens_out = ?, cost = ? WHERE id = ?",
                (_now(), round((time.perf_counter() - t0) * 1000, 3), status, error, pack(s.output),
                 s.tokens_in, s.tokens_out, s.cost, sid))


class Step:
    def __init__(self, run: Run, step_id: str):
        self.run, self.id = run, step_id
        self.output: Any = None
        self.tokens_in: int | None = None
        self.tokens_out: int | None = None
        self.cost: float | None = None

    def usage(self, tokens_in: int | None = None, tokens_out: int | None = None, cost: float | None = None) -> None:
        self.tokens_in, self.tokens_out, self.cost = tokens_in, tokens_out, cost

    def score(self, name: str, value: float, note: str | None = None) -> None:
        self.run.log.db.execute("INSERT INTO scores (run_id, step_id, name, value, note, at) VALUES (?,?,?,?,?,?)",
                                (self.run.id, self.id, name, float(value), note, _now()))

    def step(self, name: str, **kw: Any):
        """A step inside this step."""
        return self.run.step(name, parent=self, **kw)
