"""Coming up: dates on the cards and deadlines of open chances, so kb says what is close and what slipped."""

from __future__ import annotations

import json
import threading
from datetime import date

from test_serve import ask

from knowledgebreeder.picture import Picture, cards, serve, soon

TODAY = date(2026, 11, 25)

CARDS = """
### PROJECT CARD 1
name: Saturday baking class
one_line: A weekend class for beginners; the first class runs Saturday 2026-11-28.
area: Bakery
kind: class
last_activity: 2026-11-20
source: the owner's notes
WHAT IT NEEDS
- a food-safety certificate ("before 31 October 2026") | no | Tee
- a second oven, ordered before 1 October 2026 | yes | the supplier
- flour prices checked on 2026-11-01 | no | Tee
UNFINISHED
- the class flyer | due 2026-11-28 | Tee and the designer
- the spring menu | due 15 March 2027 | Tee
OPEN DECISIONS: whether to open a second class by December 1, 2026.

### PROJECT CARD 2
name: Delivery bike
one_line: A bike for deliveries in the old town.
area: Bakery
kind: idea
last_activity: 2026-10-01
source: the owner's notes
WHAT IT NEEDS
- the city permit, no later than 2026-11-30 | no | the city office
"""


def _cards():
    return {c["name"]: c for c in cards.parse(CARDS)}


def test_dates_are_read_in_three_ways_and_impossible_ones_skipped():
    got = [d.isoformat() for d, _ in soon.dates_in(
        "on 2026-11-28, or 23rd October 2026, or November 3, 2026, but never 2026-02-31 or 31 February 2026")]
    assert got == ["2026-11-28", "2026-10-23", "2026-11-03"]


def test_what_is_close_comes_first_and_what_slipped_is_named():
    rows = soon.coming(_cards(), TODAY, chances=[{"deadline": "2026-12-15", "what": "Cairo Food Makers Fund"},
                                                  {"deadline": "2026-11-20", "what": "an old call"}])
    seen = [(r["kind"], r["card"], r["what"], r["days"], r["who"]) for r in rows]
    assert seen == [
        ("missed", "Saturday baking class", 'a food-safety certificate ("before 31 October 2026")', -25, "Tee"),
        ("deadline", "Saturday baking class", "the class flyer", 3, "Tee and the designer"),
        ("deadline", "Delivery bike", "the city permit, no later than 2026-11-30", 5, "the city office"),
        ("deadline", "Saturday baking class", "whether to open a second class by December 1, 2026.", 6, ""),
        ("chance", "", "Cairo Food Makers Fund", 20, ""),
    ]
    # the one line and the unfinished flyer give the same date: one row, the more exact one
    # a met need, a past date with no deadline word, and a date too far ahead are left out
    assert all("oven" not in r["what"] and "flour" not in r["what"] and "spring" not in r["what"] for r in rows)
    assert soon.when_words(0) == "today" and soon.when_words(1) == "tomorrow" and soon.when_words(-25) == "25 days ago"
    assert soon.when_words(3, "ar") == "بعد 3 أيام" and soon.when_words(-25, "ar") == "منذ 25 يومًا"


def test_the_page_opens_with_coming_up(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    pic = Picture()
    pic.add(cards.parse(CARDS), recorded="2026-11-24")
    pic.save(w / "picture.json")
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        _, _, doc = ask(kb, "GET", "/")
        box = doc.split('id="soon"')[1].split("</section>")[0]
        assert doc.index('id="soon"') < doc.index('id="inbox"') and doc.index('id="soon"') < doc.index('id="waits"')
        assert "Slipped, 25 days ago, and still open · Sat 31 Oct</span> Waits on you." in box
        assert "Due in 3 days · Sat 28 Nov</span> Waits on <bdi>you and the designer</bdi>." in box
        _, _, ar = ask(kb, "GET", "/?lang=ar")
        assert "قريبًا" in ar and "ينتظر: <bdi>the city office</bdi>." in ar
        (w / "picture.json").write_text(json.dumps({"cards": {}}), encoding="utf-8")
        assert 'id="soon"' not in ask(kb, "GET", "/")[2]
    finally:
        srv.shutdown()
        srv.server_close()
