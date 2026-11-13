"""Reading the run log: what happened, who is best, and what got worse where."""

from __future__ import annotations

import json
from typing import Any

from .log import RunLog


def _rows(log: RunLog, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in log.db.execute(sql, args).fetchall()]


def _unpack(row: dict, *keys: str) -> dict:
    for k in keys:
        if row.get(k):
            row[k] = json.loads(row[k])
    return row


def runs(log: RunLog, task: str | None = None, limit: int = 20) -> list[dict]:
    """Newest first, with step count, totals and run-level scores."""
    out = _rows(log, """
        SELECT r.id, r.task, r.label, r.subject, r.started, r.status,
               COUNT(s.id) AS steps, SUM(s.status = 'failed') AS failed_steps,
               ROUND(SUM(s.duration_ms), 1) AS duration_ms,
               SUM(s.tokens_in) AS tokens_in, SUM(s.tokens_out) AS tokens_out, ROUND(SUM(s.cost), 4) AS cost
        FROM runs r LEFT JOIN steps s ON s.run_id = r.id
        WHERE (? IS NULL OR r.task = ?) GROUP BY r.id ORDER BY r.started DESC, r.rowid DESC LIMIT ?""",
                (task, task, limit))
    for r in out:
        r["scores"] = {x["name"]: x["value"] for x in _rows(
            log, "SELECT name, value FROM scores WHERE run_id = ? AND step_id IS NULL ORDER BY id", (r["id"],))}
    return out


def show(log: RunLog, run_id: str, payloads: bool = False) -> dict:
    """One run with its steps in order. ``payloads`` adds each step's input and output."""
    rid = log.get(run_id).id
    run = _unpack(_rows(log, "SELECT * FROM runs WHERE id = ?", (rid,))[0], "meta")
    cols = "*" if payloads else ("id, parent_id, name, worker, version, subject, started, duration_ms, status, error,"
                                 " tokens_in, tokens_out, cost")
    steps = _rows(log, f"SELECT {cols} FROM steps WHERE run_id = ? ORDER BY started, rowid", (rid,))
    by_step: dict[str, dict] = {}
    for x in _rows(log, "SELECT step_id, name, value FROM scores WHERE run_id = ? ORDER BY id", (rid,)):
        by_step.setdefault(x["step_id"] or "", {})[x["name"]] = x["value"]
    for s in steps:
        s["scores"] = by_step.get(s["id"], {})
        if payloads:
            _unpack(s, "input", "output", "meta")
    run["scores"] = by_step.get("", {})
    run["steps"] = steps
    return run


def workers(log: RunLog, task: str | None = None, score: str | None = None) -> list[dict]:
    """Leaderboard: one row per worker and version, across every run of the task.

    With ``score``, rows are ranked by that score's mean; ``n_scored`` says how
    many steps the mean rests on, so a lucky single run is easy to spot.
    """
    out = _rows(log, """
        SELECT s.worker, s.version, COUNT(*) AS steps, SUM(s.status = 'failed') AS failed,
               ROUND(AVG(s.duration_ms), 1) AS mean_ms, SUM(s.tokens_in) AS tokens_in,
               SUM(s.tokens_out) AS tokens_out, ROUND(SUM(s.cost), 4) AS cost
        FROM steps s JOIN runs r ON r.id = s.run_id
        WHERE s.worker IS NOT NULL AND (? IS NULL OR r.task = ?)
        GROUP BY s.worker, s.version""", (task, task))
    for w in out:
        sc = _rows(log, """
            SELECT c.name, ROUND(AVG(c.value), 4) AS mean, COUNT(*) AS n FROM scores c
            JOIN steps s ON s.id = c.step_id JOIN runs r ON r.id = s.run_id
            WHERE s.worker = ? AND s.version IS ? AND (? IS NULL OR r.task = ?) GROUP BY c.name""",
                   (w["worker"], w["version"], task, task))
        w["scores"] = {x["name"]: x["mean"] for x in sc}
        w["n_scored"] = {x["name"]: x["n"] for x in sc}
    if score:
        out.sort(key=lambda w: (-(w["scores"].get(score) if w["scores"].get(score) is not None else float("-inf")),
                                w["worker"]))
    else:
        out.sort(key=lambda w: (w["worker"], w["version"] or ""))
    return out


def _step_scores(log: RunLog, rid: str) -> dict[tuple, float]:
    """(subject, step name, score name) -> value; the last value wins when a step was repeated."""
    return {(x["subject"], x["step"], x["name"]): x["value"] for x in _rows(log, """
        SELECT s.subject, s.name AS step, c.name, c.value FROM scores c JOIN steps s ON s.id = c.step_id
        WHERE c.run_id = ? ORDER BY c.id""", (rid,))}


def compare(log: RunLog, base: str, challenger: str, tolerance: float = 1e-9) -> dict:
    """What changed between two runs, subject by subject. Higher scores are taken to be better."""
    a, b = log.get(base).id, log.get(challenger).id
    sa, sb = _step_scores(log, a), _step_scores(log, b)
    worse, better, same = [], [], 0
    for key in sorted(set(sa) & set(sb), key=lambda k: tuple(str(x) for x in k)):
        row = {"subject": key[0], "step": key[1], "score": key[2], "base": sa[key], "challenger": sb[key],
               "change": round(sb[key] - sa[key], 6)}
        if row["change"] < -tolerance:
            worse.append(row)
        elif row["change"] > tolerance:
            better.append(row)
        else:
            same += 1
    ra = {x["name"]: x["value"] for x in _rows(log, "SELECT name, value FROM scores WHERE run_id = ? AND step_id IS NULL", (a,))}
    rb = {x["name"]: x["value"] for x in _rows(log, "SELECT name, value FROM scores WHERE run_id = ? AND step_id IS NULL", (b,))}

    def totals(rid: str) -> dict:
        return _rows(log, """SELECT COUNT(*) AS steps, ROUND(SUM(duration_ms), 1) AS duration_ms, SUM(tokens_in) AS tokens_in,
                             SUM(tokens_out) AS tokens_out, ROUND(SUM(cost), 4) AS cost FROM steps WHERE run_id = ?""", (rid,))[0]

    return {"base": a, "challenger": b,
            "run_scores": {k: {"base": ra.get(k), "challenger": rb.get(k)} for k in sorted(set(ra) | set(rb))},
            "totals": {"base": totals(a), "challenger": totals(b)},
            "worse": sorted(worse, key=lambda r: r["change"]), "better": sorted(better, key=lambda r: -r["change"]),
            "unchanged": same,
            "only_in_base": sorted({str(k[0]) for k in set(sa) - set(sb)}),
            "only_in_challenger": sorted({str(k[0]) for k in set(sb) - set(sa)})}


def failures(log: RunLog, limit: int = 20) -> list[dict]:
    return _rows(log, """SELECT s.run_id, s.name, s.worker, s.version, s.subject, s.started, s.error FROM steps s
                         WHERE s.status = 'failed' ORDER BY s.started DESC LIMIT ?""", (limit,))


def export(log: RunLog, run_id: str | None = None) -> list[dict[str, Any]]:
    """Everything as plain records (one per run, step and score), for other tools to read."""
    ids = [log.get(run_id).id] if run_id else [r["id"] for r in _rows(log, "SELECT id FROM runs ORDER BY started")]
    out: list[dict] = []
    for rid in ids:
        out.append({"type": "run", **_unpack(_rows(log, "SELECT * FROM runs WHERE id = ?", (rid,))[0], "meta")})
        out += [{"type": "step", **_unpack(s, "input", "output", "meta")}
                for s in _rows(log, "SELECT * FROM steps WHERE run_id = ? ORDER BY started, rowid", (rid,))]
        out += [{"type": "score", **s} for s in _rows(log, "SELECT * FROM scores WHERE run_id = ? ORDER BY id", (rid,))]
    return out
