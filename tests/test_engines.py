"""Where your work waits: what frees the most and how long things wait, worked out from invented bakery cards."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import date

import pytest
from test_serve import ask

from knowledgebreeder.picture import Picture, engines, serve
from knowledgebreeder.picture.cards import parse

DAY = date(2026, 11, 24)

OLD = """
### PROJECT CARD
name: Bakery shop
area: Bakery
last_activity: 2026-11-01
WHAT IT NEEDS
- an oven | met? no | Tee
- a sign over the door | met? no | Tee
OPEN DECISIONS: open on Fridays or not

### PROJECT CARD
name: Bakery van
area: Bakery
last_activity: 2026-10-01
WHAT IT NEEDS
- a driver | met? no | Tee
OPEN DECISIONS: buy or lease

### PROJECT CARD
name: Flour mill
area: Bakery
last_activity: 2026-06-01
WHAT IT NEEDS
- a permit | met? partly | the council
- water | met? no | the city
UNFINISHED
- the roof | half done | unknown
"""

NOW = """
### PROJECT CARD
name: Bakery shop
area: Bakery
last_activity: 2026-11-20
WHAT IT NEEDS
- an oven | met? no | Tee (this month)
LINKS TO MY OTHER WORK
- Bakery van | delivers the bread
- Flour mill | sells it the flour

### PROJECT CARD
name: Bakery van
area: Bakery
last_activity: 2026-10-01
WHAT IT NEEDS
- a driver | met? no | Tee
- a loan | met? no | the bank
OPEN DECISIONS: buy or lease

### PROJECT CARD
name: Flour mill
area: Bakery
last_activity: 2026-06-01
WHAT IT NEEDS
- a permit | met? partly | the council
- water | met? yes | the city
UNFINISHED
- the roof | half done | unknown

### PROJECT CARD
name: Recipe book
area: Bakery
last_activity: 2026-11-01
WHAT IT NEEDS
- an editor | met? no | unknown
"""


def bakery() -> Picture:
    pic = Picture()
    pic.add(parse(OLD), recorded="2026-11-01")
    pic.add(parse(NOW), recorded="2026-11-20")
    return pic


def test_what_waits_on_whom_and_what_each_would_free():
    f = engines.frees(bakery())
    assert f["waiting"] == 5 and f["cards"] == 4                    # met water is not waiting; partly met is
    assert f["you"] == {"needs": 2, "cards": 2, "free": 1}
    rows = [(r["who"], r["you"], r["nobody"], r["needs"], r["cards"], r["free"]) for r in f["by"]]
    assert rows == [("Tee", True, False, 2, 2, ["Bakery shop"]),    # the van still waits on the bank too
                    ("", False, True, 1, 1, ["Recipe book"]),
                    ("the council", False, False, 1, 1, ["Flour mill"]),
                    ("the bank", False, False, 1, 1, [])]
    # One step from free: the card tied to most others comes first.
    assert [(x["card"], x["need"], x["you"]) for x in f["one_step"]] == [
        ("Bakery shop", "an oven", True), ("Flour mill", "a permit", False), ("Recipe book", "an editor", False)]


def test_how_long_things_wait_from_the_versions_kb_keeps():
    c = engines.clock(bakery(), DAY)
    assert c["open"] == {"needs": 5, "decisions": 1, "unfinished": 1, "total": 7}
    # Closed: the sign and the Friday decision left the shop, and the mill's water became met. Opened: the van's loan.
    assert (c["closed"], c["opened"], c["since"], c["days"], c["ready"]) == (3, 1, "2026-11-01", 23, True)
    assert c["per_week"] == pytest.approx(3 * 7 / 23) and c["wait_weeks"] == pytest.approx(7 / (3 * 7 / 23))
    assert not c["growing"]
    assert [(q["card"], q["open"], q["days"]) for q in c["quiet"]] == [
        ("Flour mill", 2, 176), ("Bakery van", 3, 54), ("Recipe book", 1, 23), ("Bakery shop", 1, 4)]
    assert "about 0.9 a week" in engines.md(engines.run(bakery(), DAY)) and "about 7.7 weeks" in engines.pace(c)


def test_the_pace_waits_for_two_weeks_of_versions_and_says_so():
    pic = Picture()
    pic.add(parse(OLD), recorded="2026-11-20")
    pic.add(parse(NOW), recorded="2026-11-23")
    c = engines.clock(pic, DAY)
    assert c["days"] == 4 and not c["ready"] and c["per_week"] is None
    text = engines.md(engines.run(pic, DAY))
    assert "Days kb has kept versions of your cards: 4. After 14 it can tell your pace." in text
    assert "Opened:" not in text                                  # early counts are mostly cards written out in detail


def test_a_picture_with_nothing_waiting():
    pic = Picture()
    pic.add(parse("### PROJECT CARD\nname: Done thing\nlast_activity: 2026-11-01\nWHAT IT NEEDS\n- a key | met? yes | me\n"))
    r = engines.run(pic, DAY)
    assert r["frees"]["waiting"] == 0 and r["frees"]["you"] is None and r["clock"]["open"]["total"] == 0
    assert "No card has a need waiting." in engines.md(r)


@pytest.fixture()
def kb(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    bakery().save(w / "picture.json")
    k = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=DAY)
    srv = serve.make(k)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield k
    srv.shutdown()
    srv.server_close()


def test_the_page_shows_the_box_in_both_languages(kb):
    code, _, doc = ask(kb, "GET", "/")
    assert code == 200 and 'id="waits"' in doc and doc.count("<script") == 2
    assert "Needs that wait on you: 2 of 5. On cards: 2." in doc and "Once done, nothing is left waiting on: Bakery shop." in doc
    assert "Name who does these" in doc and "waits on you" in doc and "waits on nobody named" in doc and "Quiet longest" in doc
    assert doc.index('id="waits"') < doc.index('id="where"')
    code, _, doc = ask(kb, "GET", "/?lang=ar")
    assert code == 200 and "أين ينتظر عملك" in doc and doc.count('dir="rtl"') == 1 and "⁨" in doc
    assert set(serve.LABELS["ar"]) == set(serve.LABELS["en"])


def test_the_box_is_worked_out_again_only_when_the_cards_change(kb):
    first = kb.waits()
    assert kb.waits() is first
    pic = Picture.load(kb.picture)
    pic.add(parse("### PROJECT CARD\nname: Cake stand\nlast_activity: 2026-11-24\nWHAT IT NEEDS\n- wood | met? no | me\n"))
    pic.save(kb.picture)
    again = kb.waits()
    assert again is not first and again["frees"]["you"]["needs"] == 3


def test_no_cards_means_no_box_and_a_broken_file_says_so(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    k = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=DAY)
    assert k.waits_html("en") == ""
    (w / "picture.json").write_text("{not json", encoding="utf-8")
    assert "Could not read your cards" in k.waits_html("en")


def test_the_command_prints_the_same(tmp_path):
    p = tmp_path / "picture.json"
    bakery().save(p)
    out = subprocess.run([sys.executable, "-m", "knowledgebreeder.cli", "picture", "--file", str(p), "engines",
                          "--today", "2026-11-24", "--json"], capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    assert r["frees"]["you"]["needs"] == 2 and r["clock"]["open"]["total"] == 7
    text = subprocess.run([sys.executable, "-m", "knowledgebreeder.cli", "picture", "--file", str(p), "engines",
                           "--today", "2026-11-24"], capture_output=True, text=True, check=True).stdout
    assert text.startswith("# Where your work waits") and "- Bakery shop: an oven (waits on you)" in text
