"""The run log: recording, failure capture, leaderboard, comparison and the command line."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from knowledgebreeder.cli import main
from knowledgebreeder.runlog import RunLog, query
from knowledgebreeder.runlog import log as logmod

FIX = Path(__file__).parent / "fixtures"
SHEETS = {"page_01": (0.9, 0.6), "page_02": (0.8, 0.9), "page_03": (0.7, 0.7)}   # subject -> (old, new) flow_f1


@pytest.fixture()
def two_runs(tmp_path):
    log = RunLog(tmp_path / "runs.db")
    ids = []
    for which, (worker, version) in enumerate((("reader_a", "1.0"), ("reader_b", "0.1"))):
        with log.run("read-pid", label=worker, subject="plant.pdf", note="test") as run:
            for subject, vals in SHEETS.items():
                with run.step("read", worker=worker, version=version, subject=subject, input={"page": subject}) as s:
                    s.output = {"ok": True}
                    s.usage(tokens_in=1000, tokens_out=200, cost=0.01)
                    s.score("flow_f1", vals[which])
            run.score("flow_f1", sum(v[which] for v in SHEETS.values()) / 3)
        ids.append(run.id)
    return log, ids


def test_records_runs_steps_scores(two_runs):
    log, (a, _b) = two_runs
    rows = query.runs(log)
    assert [r["label"] for r in rows] == ["reader_b", "reader_a"]                 # newest first
    assert rows[1]["steps"] == 3 and rows[1]["tokens_in"] == 3000 and rows[1]["cost"] == 0.03
    assert rows[1]["scores"]["flow_f1"] == pytest.approx(0.8) and rows[1]["status"] == "ok"
    shown = query.show(log, a[:10], payloads=True)                              # an id prefix is enough
    assert [s["subject"] for s in shown["steps"]] == list(SHEETS) and shown["meta"] == {"note": "test"}
    assert shown["steps"][0]["input"] == {"page": "page_01"} and shown["steps"][0]["scores"] == {"flow_f1": 0.9}
    assert shown["steps"][0]["duration_ms"] >= 0


def test_failure_is_recorded_and_raised(tmp_path):
    log = RunLog(tmp_path / "runs.db")
    with pytest.raises(ValueError):
        with log.run("t") as run:
            with run.step("boom", worker="w"):
                raise ValueError("bad sheet")
    r = query.runs(log)[0]
    assert r["status"] == "failed" and r["failed_steps"] == 1
    f = query.failures(log)[0]
    assert f["name"] == "boom" and "ValueError: bad sheet" in f["error"]


def test_leaderboard(two_runs):
    log, _ = two_runs
    board = query.workers(log, task="read-pid", score="flow_f1")
    assert [w["worker"] for w in board] == ["reader_a", "reader_b"]             # 0.80 beats 0.733
    assert board[0]["scores"]["flow_f1"] == pytest.approx(0.8) and board[0]["n_scored"]["flow_f1"] == 3
    assert board[1]["failed"] == 0 and board[1]["tokens_out"] == 600
    assert query.workers(log, task="other") == []


def test_compare_names_the_sheets_that_got_worse(two_runs):
    log, (a, b) = two_runs
    c = query.compare(log, a, b)
    assert [(r["subject"], r["change"]) for r in c["worse"]] == [("page_01", pytest.approx(-0.3))]
    assert [r["subject"] for r in c["better"]] == ["page_02"] and c["unchanged"] == 1
    assert c["run_scores"]["flow_f1"]["base"] > c["run_scores"]["flow_f1"]["challenger"]
    assert c["totals"]["base"]["steps"] == 3
    with pytest.raises(KeyError):
        query.compare(log, a, "run_nope")


def test_nested_steps_and_large_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr(logmod, "MAX_PAYLOAD", 100)
    log = RunLog(tmp_path / "runs.db")
    with log.run("t") as run:
        with run.step("outer") as outer:
            with outer.step("inner") as inner:
                inner.output = {"blob": "x" * 500}
    steps = query.show(log, run.id, payloads=True)["steps"]
    assert steps[1]["parent_id"] == steps[0]["id"]
    assert steps[1]["output"]["_truncated"] and steps[1]["output"]["chars"] > 500 and len(steps[1]["output"]["sha256"]) == 64


def test_two_processes_can_share_a_run(tmp_path):
    db = tmp_path / "runs.db"
    run = RunLog(db).start("t")
    other = RunLog(db).get(run.id)                                               # a second connection
    other.record("extract", worker="model-x", subject="page_01", tokens_in=5, scores={"tags_f1": 0.5})
    run.end()
    assert query.show(RunLog(db), run.id)["steps"][0]["scores"] == {"tags_f1": 0.5}


def test_export_is_plain_records(two_runs, tmp_path):
    log, (a, _b) = two_runs
    rows = query.export(log, a)
    assert [r["type"] for r in rows].count("step") == 3 and rows[0]["type"] == "run"
    assert sum(r["type"] == "score" for r in rows) == 4
    json.dumps(rows)


def test_cli_roundtrip(tmp_path, capsys):
    db = str(tmp_path / "runs.db")
    assert main(["log", "--db", db, "runs"]) == 2                               # no log yet: a clear error, no empty file
    assert not Path(db).exists()
    capsys.readouterr()
    assert main(["log", "--db", db, "start", "--task", "extract", "--label", "manual"]) == 0
    rid = capsys.readouterr().out.strip()
    out_file = tmp_path / "out.json"
    out_file.write_text('{"tags": 12}')
    assert main(["log", "--db", db, "step", rid, "--name", "extract", "--worker", "some-model", "--subject", "page_01",
                 "--tokens-in", "900", "--tokens-out", "100", "--ms", "1500", "--output-file", str(out_file),
                 "--score", "tags_f1=0.9"]) == 0
    assert main(["log", "--db", db, "end", rid, "--score", "tags_f1=0.9"]) == 0
    capsys.readouterr()
    assert main(["log", "--db", db, "show", rid, "--payloads"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["status"] == "ok" and shown["scores"] == {"tags_f1": 0.9}
    assert shown["steps"][0]["output"] == {"tags": 12} and shown["steps"][0]["duration_ms"] == 1500
    for cmd in (["runs"], ["workers", "--score", "tags_f1"], ["failures"], ["export"], ["compare", rid, rid]):
        assert main(["log", "--db", db, *cmd]) == 0
    assert main(["log", "--db", db, "show", "run_missing"]) == 2


def test_score_and_read_write_to_the_log(tmp_path, capsys):
    db = str(tmp_path / "runs.db")
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"tags": ["TK-101", "P-101"], "feeds": [["TK-101", "P-101"]], "loops": {}}))
    assert main(["score", str(FIX / "demo_graph.json"), str(gold), "--runlog", db, "--worker", "seed", "--version", "0.1.0",
                 "--subject", "D-001"]) == 0
    log = RunLog(db)
    board = query.workers(log, score="flow_f1")
    assert board[0]["worker"] == "seed" and 0 < board[0]["scores"]["flow_f1"] < 1
    assert "loop_recall" not in board[0]["scores"]                               # nothing to score, so nothing recorded
    assert query.runs(log)[0]["scores"]["tags_f1"] > 0

    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    pdf = tmp_path / "p.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(400, 300)); c.line(50, 150, 350, 150); c.save()
    assert main(["read", str(pdf), "--out", str(tmp_path / "s.json"), "--runlog", db]) == 0
    step = query.show(log, query.runs(log, task="read")[0]["id"], payloads=True)["steps"][0]
    assert step["worker"] == "vector_geometry" and step["subject"] == "page_01" and step["output"]["stats"]["segments"] == 1
    assert sqlite3.connect(db).execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "1"
