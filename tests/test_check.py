"""Is the picture ready for a model? Five questions asked of the demo cards, and the ticks that test whether it matters.

The cards are invented (tests/fixtures/demo_cards.md). The model is a stand-in.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
from standin import StandIn
from test_advise_scout import CARDS, _eid, _setup

from knowledgebreeder.cli import main
from knowledgebreeder.picture import Picture, cards, check, page
from knowledgebreeder.runlog import RunLog

TODAY = date(2026, 11, 22)


@pytest.fixture()
def pic():
    return Picture.load(CARDS)


def test_five_questions_of_the_demo_cards(pic):
    r = check.cards(pic)
    oud = r["oud-practice-log"]
    assert oud["level"] == "weak" and oud["filled"] == 2 and oud["source"] == "memory"
    assert oud["gaps"] == ["it does not say when it was last worked on", "2 of 12 parts filled in",
                           "its facts come from memory only"]
    assert r["dar-bakery-order-book"]["level"] == "ready" and not r["dar-bakery-order-book"]["gaps"]
    assert check.weak(pic) == {"oud-practice-log"}
    c = check.check(pic, today=TODAY)
    assert c["levels"] == {"ready": 4, "thin": 0, "weak": 1} and c["current"]["not"] == ["Oud practice log"]
    assert c["provenance"] == {"named": 4, "memory": ["Oud practice log"], "none": []}
    assert c["one_name"]["no_card"] == ["Grandmother's cookbook"] and c["owner"]["named"] == []
    md = check.check_md(c)
    assert "1 weak" in md and "- Oud practice log: it does not say when" in md
    assert "No advice run has recorded its cards' readiness yet" in md


def test_one_project_under_two_names_an_owner_and_areas_written_two_ways():
    text = """### PROJECT CARD
name: Recipe cards
one_line: Cards for the class.
area: Bakery
owner: the school
source: memory and my head

### PROJECT CARD
name: Recipe cards app
one_line: The same cards on a phone.
area: bakery
source: unknown

### PROJECT CARD
name: Shop sign
aliases: the board
one_line: A painted board.
area: Bakeries

### PROJECT CARD
name: The board
one_line: The board by the door.
area: Shop
"""
    p = Picture()
    p.add(cards.parse(text, "t.md"))
    pairs = {(a, b): why for a, b, why in check.same_names(p)}
    assert pairs == {("recipe-cards", "recipe-cards-app"): "one name holds the other",
                     ("shop-sign", "the-board"): "a name of one is an alias of the other"}
    assert check.areas(p) == [["Bakeries", "Bakery", "bakery"]]
    r = check.cards(p)
    assert r["recipe-cards"]["owner"] == "the school" and r["recipe-cards"]["source"] == "memory"
    assert r["recipe-cards-app"]["source"] == "none" and "it may be the same project as Recipe cards" in r["recipe-cards-app"]["gaps"]
    md = check.check_md(check.check(p, today=TODAY))
    assert "\"Recipe cards\" and \"Recipe cards app\" may be one project" in md and "1 of 4 name an owner" in md
    assert "one area written 3 ways" in md


def test_a_card_that_links_to_the_other_says_they_are_two_works():
    text = """### PROJECT CARD
name: Bakery
one_line: The shop.
area: Food
last_activity: 2026-11-20
source: my notes
LINKS TO MY OTHER WORK: Bakery van | how the bread reaches the town

### PROJECT CARD
name: Bakery van
one_line: The van.
area: Food
last_activity: 2026-11-20
source: my notes

### PROJECT CARD
name: Bakery cards
one_line: Recipe cards.
area: Food
last_activity: 2026-11-20
source: my notes
"""
    p = Picture()
    p.add(cards.parse(text, "t.md"))
    pairs = {(a, b): why for a, b, why in check.same_names(p)}
    assert pairs == {("bakery", "bakery-cards"): "one name holds the other"}       # no link, still asked about
    r = check.cards(p)
    assert not any("same project" in g for g in r["bakery-van"]["gaps"])
    assert "it may be the same project as Bakery cards" in r["bakery"]["gaps"]


def two_pieces(model, system, user):
    oud, driver = _eid(user, "record one piece a month"), _eid(user, "a delivery driver")
    return json.dumps({"advice": [
        {"move": "Record one oud piece this month.", "why": "The idea is waiting.", "cites": [oud], "first_step": "Pick it."},
        {"move": "Ask a neighbour to drive on Fridays.", "why": "Orders need a driver.", "cites": [driver],
         "first_step": "Ask today."}]})


def test_advice_records_weak_cards_and_your_ticks_test_whether_they_matter(tmp_path, capsys, monkeypatch):
    with StandIn(two_pieces) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv)
        assert main(["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db, "--today",
                     "2026-11-22", "--lessons", str(tmp_path / "none.md")]) == 0
    run_id = re.search(r"Recorded as (run_\w+)", capsys.readouterr().out).group(1)
    log = RunLog(db)
    try:
        inp = json.loads(log.db.execute("SELECT input FROM steps WHERE run_id = ?", (run_id,)).fetchone()["input"])
        data = page.gather(log, run_id)
    finally:
        log.close()
    assert inp["weak_cards"] == ["Oud practice log"]
    marked = [e["text"] for e in inp["evidence"] if e.get("weak")]
    assert marked and all("Oud" in t for t in marked)
    assert data["readiness"] and "rests only on weak cards" not in json.dumps(inp)          # the model is not told
    doc = page.build(data, lang="en")
    assert doc.count('class="check weak"') == 1

    base = ["picture", "--file", pic, "check", "--runlog", db, "--today", "2026-11-22"]
    assert main(base) == 0
    assert "No advice run has recorded" not in capsys.readouterr().out
    assert main(["picture", "rate", run_id, "2", "--runlog", db, "--lessons", str(tmp_path / "none.md")]) == 0
    capsys.readouterr()
    assert main(base) == 0
    out = capsys.readouterr().out
    assert "Pieces resting only on weak cards: you would act on 0 of 1 (0%). The rest: 1 of 1 (100%)" in out
    assert "too few to read anything into" in out
    monkeypatch.setattr(check, "MIN_PIECES", 1)
    assert main(base + ["--json"]) == 0
    t = json.loads(capsys.readouterr().out)["ticks"]
    assert t == {"runs": 1, "weak": {"acted": 0, "pieces": 1}, "rest": {"acted": 1, "pieces": 1}, "enough": True}
