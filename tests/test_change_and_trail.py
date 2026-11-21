"""Your own version of an idea, kept with your verdict, and the run's Vn-trail read back from the run log.

You can say an idea your way under the piece itself; it is saved with the ticks, shown on the idea afterwards,
and, if you say so, becomes a lesson for every run. After Save the page says back what kb recorded, your words
included. The trail folds the whole run into the eight fields of a Vn-trail. The models are stand-ins here.
"""

from __future__ import annotations

import json
import re
import threading

import pytest
from standin import StandIn
from test_advise_scout import _setup, two_minds
from test_serve import ask

from knowledgebreeder.cli import main
from knowledgebreeder.picture import lessons, page, serve, trail
from knowledgebreeder.runlog import RunLog, query

MINE = "Not in the old app: keep it as a shared capability in kb."


@pytest.fixture()
def made(tmp_path, capsys):
    """A run log with one advice run from two models, small and big, three pieces each."""
    with StandIn(two_minds) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv)
        assert main(["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db,
                     "--today", "2026-11-21", "--models", "small,big"]) == 0
    run_id = re.search(r"Recorded as (run_\w+)", capsys.readouterr().out).group(1)
    return run_id, db, str(tmp_path / "w" / "lessons.md")


def _scores(db, run_id):
    log = RunLog(db)
    try:
        return {s["worker"]: s["scores"] for s in query.show(log, run_id)["steps"]}
    finally:
        log.close()


def _data(db, run_id):
    log = RunLog(db)
    try:
        return page.gather(log, run_id)
    finally:
        log.close()


def test_a_change_is_kept_with_the_rating_and_can_become_a_lesson(made, capsys):
    run_id, db, les = made
    base = ["picture", "rate", run_id, "--worker", "small", "--runlog", db, "--lessons", les, "--today", "2026-11-21"]
    assert main(base + ["2", "--keep", "1"]) == 2                               # a lesson needs your words first
    assert "a lesson can only be kept from a piece you changed" in capsys.readouterr().err
    assert main(base + ["2", "--change", "9", "x"]) == 2
    assert "pieces 1 to 3" in capsys.readouterr().err
    assert main(base + ["2", "--change", "one", "x"]) == 2
    assert "--change takes a piece number" in capsys.readouterr().err
    assert "would_act" not in _scores(db, run_id)["small"]                       # nothing half-written
    assert not lessons.read(les)

    assert main(base + ["2", "--why", "the class is soon", "--change", "1", f"  {MINE} ", "--keep", "1",
                        "--change", "3", "Merge the two customer lists first."]) == 0
    out = capsys.readouterr().out
    assert f"Your change to #1: {MINE}" in out and f"Kept as a lesson in {les}" in out
    assert "Your change to #3: Merge the two customer lists first." in out
    assert lessons.read(les) == [MINE]                                           # only the one you kept

    d = _data(db, run_id)
    small = next(a for a in d["answers"] if a["worker"] == "small")
    got = {p["n"]: (p.get("change"), p.get("kept")) for p in small["pieces"]}
    assert got == {1: (MINE, True), 2: (None, None), 3: ("Merge the two customer lists first.", False)}
    assert small["rated"] == [2] and small["why"] == "the class is soon"

    doc = page.build(d, lang="en")                                               # the file you open on the laptop
    assert doc.count('class="changed"') == 2 and "kept as a lesson for every run" in doc
    assert "Your words:</b> <span dir=\"auto\">the class is soon" in doc
    assert f'Your change <bdi>#1 (a lesson)</bdi>:</b> <span dir="auto">{MINE}' in doc and 'id="rec-0"' in doc
    assert 'Your change <bdi>#3</bdi>:</b> <span dir="auto">Merge the two' in doc
    assert doc.count('class="change-text"') == 3                                 # big is still open to change
    ar = page.build(d, lang="ar")
    assert "تغييرك" in ar and "كلماتك" in ar and 'dir="rtl"' in ar


def test_the_phone_saves_your_change_and_says_back_what_it_recorded(made):
    run_id, db, les = made
    kb = serve.Kb(db, les, 0)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        _, _, doc = ask(kb, "GET", f"/run/{run_id}")
        assert doc.count('class="change-text"') == 6 and 'data-rec="rec-0"' in doc and 'data-rec="rec-pick"' in doc
        assert "<details class=\"box\" id=\"trail\">" in doc                       # folded away until you open it

        o = {"Origin": f"http://127.0.0.1:{kb.port}"}
        bad = [{"n": "1", "text": "x"}, {"n": 1, "text": 5}, {"n": 1, "text": "x", "lesson": "yes"}, "x"]
        for c in bad:
            assert ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": [], "changes": [c]}, o)[0] == 400
        assert ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": [], "changes": "x"}, o)[0] == 400
        code, _, said = ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": [1],
                                                      "changes": [{"n": 2, "text": " ", "lesson": True}]}, o)
        assert code == 400 and "a lesson can only be kept" in json.loads(said)["error"]
        assert "would_act" not in _scores(db, run_id)["big"]

        code, _, said = ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": [1, 2],
                                                      "why": "prices first",
                                                      "changes": [{"n": 2, "text": MINE, "lesson": True},
                                                                  {"n": 3, "text": "Ask one driver, not three."}]}, o)
        r = json.loads(said)
        assert code == 200 and r["changes"] == [[2, MINE], [3, "Ask one driver, not three."]]
        assert r["kept"] == [2] and r["lessons_added"] == 1 and lessons.read(les) == [MINE]

        _, _, doc = ask(kb, "GET", f"/run/{run_id}")
        assert 'class="rate done" id="rec-1"' in doc and "Your words:</b> <span dir=\"auto\">prices first" in doc
        assert f"Your change:</b> <span dir=\"auto\">{MINE}" in doc and doc.count('class="change-text"') == 3
        assert "DIALOGUE" in doc
        assert MINE in ask(kb, "GET", "/")[2]                                    # the lesson is on the first page too
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_trail_reads_who_did_what_from_the_run_log(made, capsys):
    run_id, db, les = made
    t = trail.entries(_data(db, run_id))
    assert [e["n"] for e in t] == ["V0: the ask", "V1: small's answer", "V2: big's answer", "forthcoming"]
    assert all(set(e) == set(trail.FIELDS) for e in t)                           # the eight fields, every time
    assert trail.origins(t) == {"HUMAN": 1, "AI": 2, "DIALOGUE": 0}
    assert "waiting on your verdict: small, big" in t[-1]["delta_plus"]
    assert "sent to small, big" in t[0]["delta_plus"] and "silicon: nothing yet" in t[0]["split"]

    assert main(["picture", "rate", run_id, "1", "--worker", "small", "--runlog", db, "--lessons", les,
                 "--change", "2", MINE, "--keep", "2"]) == 0
    assert main(["picture", "rate", run_id, "none", "--worker", "big", "--runlog", db, "--lessons", les]) == 0
    assert main(["models", "--file", db.replace("runs.db", "models.json"), "pick", run_id, "small", "--db", db]) == 0
    capsys.readouterr()
    t = trail.entries(_data(db, run_id))
    assert [e["origin"] for e in t] == ["HUMAN", "AI", "AI", "HUMAN", "DIALOGUE", "HUMAN", "HUMAN"]
    verdict, change, _, pick = t[3], t[4], t[5], t[6]
    assert verdict["delta_plus"] == "you would act on #1" and verdict["delta_minus"] == "you would not act on #2, #3"
    assert verdict["delta_reframed"] == "you changed #2 (next entries)"
    assert change["n"] == "V4: your change to small #2" and change["delta_plus"] == "a lesson for every run"
    assert change["delta_reframed"].startswith("from “Finish cards seven to twelve") and MINE in change["delta_reframed"]
    assert pick["delta_plus"] == "picked small" and pick["delta_minus"] == "not big"
    assert t[5]["delta_plus"] == "none"                                         # big: acted on nothing

    assert main(["picture", "trail", run_id, "--runlog", db, "--json"]) == 0
    rows = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert len(rows) == 7 and rows[4]["origin"] == "DIALOGUE" and rows[0]["run"] == run_id
    assert main(["picture", "trail", "--runlog", db]) == 0                       # newest run, as a table
    md = capsys.readouterr().out
    assert f"# Vn-trail: {run_id}" in md and "HUMAN 4 · AI 2 · DIALOGUE 1" in md and "| Vn | Trigger |" in md
    assert main(["picture", "trail", "--all", "--runlog", db, "--lang", "ar"]) == 0
    assert "المصدر" in capsys.readouterr().out
    assert main(["picture", "trail", "--runlog", str(db) + ".none"]) == 2

    doc = page.build(_data(db, run_id), lang="ar")
    assert 'id="trail"' in doc and "مسار هذا التشغيل" in doc and "o-dialogue" in doc
