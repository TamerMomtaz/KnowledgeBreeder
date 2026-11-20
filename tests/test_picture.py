"""The whole picture: reading cards, tying names together, the four reports, the town page and the command line."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from knowledgebreeder.cli import main
from knowledgebreeder.picture import Picture, cards, reports, town

FIX = Path(__file__).parent / "fixtures" / "demo_cards.md"
TODAY = date(2026, 11, 20)


@pytest.fixture()
def pic():
    return Picture.load(FIX)


def test_reads_both_layouts_and_nothing_else(pic):
    assert [c["name"] for c in pic.cards.values()] == [
        "Dar Bakery order book", "Dar Bakery stock sheet", "Saturday baking class",
        "Recipe cards (كروت الوصفات)", "Oud practice log"]
    book, sheet = pic.cards["dar-bakery-order-book"], pic.cards["dar-bakery-stock-sheet"]
    assert book["purpose"]["my_goal"] == '"never lose an order again"'
    assert [f[0] for f in book["exists"]] == ["Order list", "Customer list with phone numbers", "Printed order form"]
    assert book["needs"][0] == ["a delivery driver", "met? no", "by what: nobody yet"]
    assert book["unfinished"][0][-1].endswith("nobody picked it up again")          # a wrapped line joins its item
    assert book["notes"] == ["Notes: the folder is in the shop."]
    assert book["last_date"] == "2026-11-10"                                         # the newest date on the line
    assert sheet["purpose"] == {"problem": "running out of flour on a Friday", "who_it_serves": "Nour",
                                "my_goal": "unknown"}
    assert sheet["parts"] == [['the rule "count once; order once"', "any shelf could use it"]]   # quoted semicolon kept
    assert [f[0] for f in sheet["themes"]] == ["write it down once", "counting on a fixed day."]


def test_unknown_is_kept_as_a_fact_not_filled_in(pic):
    oud = pic.cards["oud-practice-log"]
    assert oud["last_date"] is None and oud["exists"] == [] and oud["links"] == []
    assert {"exists", "can_do", "needs", "links", "my_goal", "problem"} <= set(oud["unknown"])
    assert oud["ideas"] == [["record one piece a month"]]
    cls = pic.cards["saturday-baking-class"]
    assert cls["decisions"] == []                                                    # a template hint is not an item
    assert "my_goal" in cls["unknown"] and "unfinished" in cls["unknown"]
    assert cards.met("met? no") == "no" and cards.met("met? partly") == "partly"
    assert cards.met("is it met today? yes") == "yes" and cards.met("unknown") == "unknown"


def test_names_resolve_to_cards(pic):
    assert pic.resolve("the Saturday class") == ["saturday-baking-class"]
    assert pic.resolve("Recipe cards") == ["recipe-cards-كروت-الوصفات"]
    assert pic.resolve("recipe deck") == ["recipe-cards-كروت-الوصفات"]              # an alias given on the card
    assert pic.resolve("كروت الوصفات") == ["recipe-cards-كروت-الوصفات"]
    assert pic.resolve("Dar Bakery stock sheet and Oud practice log") == ["dar-bakery-stock-sheet", "oud-practice-log"]
    assert pic.resolve("Grandmother's cookbook") == []
    assert pic.resolve("all my teaching") == []                                      # a collective, not a card
    assert pic.resolve("Dar Bakery") == []                                           # two cards fit equally: left open
    assert pic.unclear("Dar Bakery") == ["dar-bakery-order-book", "dar-bakery-stock-sheet"]
    deg = pic.degree()
    assert deg["oud-practice-log"] == 0 and deg["saturday-baking-class"] == 2 and deg["dar-bakery-order-book"] == 2


def test_overlaps(pic):
    o = reports.overlaps(pic)
    themes = {t["theme"]: t["projects"] for t in o["themes"]}
    assert themes["Arabic first"] == ["Dar Bakery order book", "Recipe cards (كروت الوصفات)", "Saturday baking class"]
    assert themes["write it down once"] == ["Dar Bakery order book", "Dar Bakery stock sheet"]
    assert "hands before theory" not in themes                                       # one project is not an overlap
    pairs = {tuple(s["ids"]): s["says"] for s in o["stated"]}
    twice = pairs[("dar-bakery-order-book", "dar-bakery-stock-sheet")]
    assert "kept twice" in twice and "built separately" in twice                     # both cards' words, one row
    assert "overlaps_md" and reports.overlaps_md(o).startswith("# Overlaps")


def test_gaps(pic):
    pic.add_area("Painting")
    g = reports.gaps(pic, TODAY)
    needs = {(n["project"], n["need"]): n["met"] for n in g["unmet_needs"]}
    assert needs[("Dar Bakery order book", "a delivery driver")] == "no"
    assert needs[("Dar Bakery stock sheet", "someone to count on Sundays")] == "partly"
    assert ("Dar Bakery order book", "a second phone") not in needs                  # met needs are not gaps
    assert g["unmet_needs"][0]["by"] == "nobody yet"
    assert g["named_without_card"] == [{"name": "Grandmother's cookbook", "named_by": ["Saturday baking class"]}]
    assert g["empty_areas"] == ["Painting"] and g["unclear_names"] == []
    assert [a["project"] for a in g["standing_alone"]] == ["Oud practice log"]
    quiet = {q["project"]: q["days"] for q in g["quiet"]}
    assert quiet == {"Oud practice log": None, "Dar Bakery stock sheet": 292}        # no date, then oldest first
    assert [d["decision"] for d in g["open_decisions"]] == ["raise prices in Ramadan or not",
                                                            "print them or keep them on the phone"]
    assert "Grandmother's cookbook" in reports.gaps_md(g)


def test_reuse(pic):
    r = reports.reuse(pic)
    assert [(x["part"], x["from"], x["to"]) for x in r["named"]] == [
        ("customer list with phone numbers", "Dar Bakery order book", "Saturday baking class")]
    assert r["named"][0]["basis"] == "the card says so"
    wide = {x["part"] for x in r["wide"]}
    assert {"the reminder one day before", 'the rule "count once; order once"', "the one-page layout"} <= wide
    assert all(m["basis"] == "word match" and len(m["shared"]) >= 2 for m in r["matched"])
    assert reports.reuse_md(r).startswith("# Reuse")


def test_brief_names_its_sources(pic):
    b = reports.brief(pic, TODAY)
    assert b and b[0]["kind"] == "reuse" and "Saturday baking class" in b[0]["move"]
    assert b[0]["source"] == ["Dar Bakery order book · REUSABLE PARTS"]
    kinds = [x["kind"] for x in b]
    assert {"reuse", "overlap", "gap", "decision", "question"} <= set(kinds)
    assert any("Arabic first" in x["move"] for x in b)                               # three projects share it
    assert any("Grandmother's cookbook" in x["move"] for x in b)
    text = reports.brief_md(b)
    assert "does not look outside the picture" in text and "From: " in text


def test_save_load_and_replace(tmp_path, pic):
    path = pic.save(tmp_path / "work" / "picture.json")
    again = Picture.load(path)
    assert again.cards == pic.cards and reports.overlaps(again) == reports.overlaps(pic)
    newer = cards.parse("PROJECT CARD\nname: Oud practice log\narea: Music\nlast_activity: 2026-11-19\n")
    assert again.add(newer) == {"added": [], "updated": ["Oud practice log"]}
    assert again.cards["oud-practice-log"]["last_date"] == "2026-11-19" and len(again.cards) == 5
    with pytest.raises(KeyError):
        Picture.load(tmp_path / "missing.json")


def test_town_is_one_private_offline_file(pic):
    pic.add_area("Painting")
    pic.add(cards.parse('PROJECT CARD\nname: Tricky </script><script>alert(1)</script> & "quotes"\narea: Music\n'
                        "WHAT IT CAN DO: break pages <img src=x onerror=alert(1)>\n"))
    page = town.build(pic, today=TODAY)
    assert len(re.findall(r'<g class="b[ "]', page)) == 6 and page.count('class="district') == 4   # one building per card
    assert "<script>alert(1)" not in page and "<img src=x" not in page        # card text cannot become markup
    assert page.count("<script") == 2 and page.count("</script>") == 2
    assert not re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", page)        # nothing is fetched
    assert "default-src 'none'" in page
    assert 'data-i18n="empty_lot"' in page                                           # the area with no card is drawn
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert set(data["reports"]) == {"brief", "overlaps", "gaps", "reuse"} and len(data["cards"]) == 6
    assert data["cards"]["saturday-baking-class"]["links"][2] == {
        "target": "Grandmother's cookbook", "how": "where the breads come from", "to": []}
    assert set(town.LABELS["ar"]) == set(town.LABELS["en"])
    arabic = town.build(pic, today=TODAY, lang="ar", title="صورة نور")
    assert '<html lang="ar" dir="rtl">' in arabic and "<title>صورة نور</title>" in arabic


def test_tall_buildings_stand_at_the_back():
    many = [{"id": f"p{i}", "name": f"Project {i}", "decisions": [], "unfinished": [], "last_date": None}
            for i in range(11)]
    svg = town.district_svg("Area", many, {f"p{i}": i for i in range(11)})
    order = re.findall(r'data-id="(p\d+)"', svg)
    assert order[0] == "p10" and order[-1] == "p0" and len(order) == 11              # drawn back to front
    assert town.short("Dar Bakery, the order book (app)") == "Dar Bakery"
    assert town.short("A very long projet name indeed") == "A very long proje…"


def test_command_line(tmp_path, capsys):
    file = str(tmp_path / "work" / "picture.json")
    assert main(["picture", "--file", file, "show"]) == 2                            # no picture yet
    assert "kb picture add" in capsys.readouterr().err
    assert main(["picture", "--file", file, "add", str(FIX), "--area", "Painting"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cards"] == 5 and len(out["added"]) == 5 and out["areas_added"] == ["Painting"]
    assert main(["picture", "--file", file, "add", str(FIX)]) == 0
    assert len(json.loads(capsys.readouterr().out)["updated"]) == 5                  # adding again replaces, never doubles
    assert main(["picture", "--file", file, "show"]) == 0
    assert json.loads(capsys.readouterr().out)["areas"] == {"Bakery": 2, "Teaching": 2, "Music": 1, "Painting": 0}
    assert main(["picture", "--file", file, "gaps", "--json", "--today", "2026-11-20"]) == 0
    assert json.loads(capsys.readouterr().out)["empty_areas"] == ["Painting"]
    for cmd in ("overlaps", "reuse", "brief"):
        assert main(["picture", "--file", file, cmd]) == 0
        assert capsys.readouterr().out.startswith("# ")
    html_path = tmp_path / "out" / "town.html"
    assert main(["picture", "--file", file, "town", "--out", str(html_path), "--lang", "ar"]) == 0
    assert "private" in capsys.readouterr().out and html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert main(["picture", "--file", str(FIX), "brief"]) == 0                       # a cards file works without adding
    assert capsys.readouterr().out.startswith("# Brief")
