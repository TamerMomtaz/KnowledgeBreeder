"""Nothing overwritten: every version of a card is kept, and what left a card is shown, not lost.

The cards are invented. The rules: nothing updated in place, two dates per fact (when it was true, when kb learned
it), a fingerprint taken at intake, and both sides of a disagreement shown.
"""

from __future__ import annotations

import json

from knowledgebreeder.cli import main
from knowledgebreeder.picture import Picture, advise, cards, changes, check, reports
from knowledgebreeder.picture.private import Private

MAY = """### PROJECT CARD
name: Corner bakery
one_line: A small bakery that sells bread by the door.
area: Bakery
kind: being built
last_activity: 2026-05-02
source: my notebook

IDEAS NOT STARTED
- a Friday bread box for the school
- sell flour by the kilo

WHAT IT NEEDS
- a second oven | no | money
- a delivery driver | no | nobody yet

OPEN DECISIONS
- open on Saturdays or not
"""

NOVEMBER = """### PROJECT CARD
name: Corner bakery
one_line: A small bakery that sells bread by the door.
area: Bakery
kind: running product
last_activity: 2026-11-10
source: my notebook

IDEAS NOT STARTED
- sell flour by the kilo, in paper bags

WHAT IT NEEDS
- a second oven | yes | bought in October
- a weekend baker | no | nobody yet
"""


def _add(tmp_path, capsys, text, day, name="bakery.md"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    pic = str(tmp_path / "work" / "picture.json")
    assert main(["picture", "--file", pic, "add", str(f), "--today", day]) == 0
    return pic, json.loads(capsys.readouterr().out)


def test_a_newer_card_keeps_the_older_one_and_says_what_left(tmp_path, capsys):
    pic, first = _add(tmp_path, capsys, MAY, "2026-05-03")
    assert first["added"] == ["Corner bakery"] and "see" not in first
    pic, same = _add(tmp_path, capsys, MAY, "2026-06-01")
    assert same["unchanged"] == ["Corner bakery"] and not same["updated"]        # the same card again changes nothing
    pic, out = _add(tmp_path, capsys, NOVEMBER, "2026-11-12")
    assert out["updated"] == ["Corner bakery"] and "kb picture changes" in out["see"]
    assert out["changed"]["Corner bakery"].startswith("3 left the card (idea: a Friday bread box for the school; "
                                                      "need: a delivery driver; open decision: open on Saturdays")
    assert "need a second oven: no → yes" in out["changed"]["Corner bakery"]

    p = Picture.load(pic)
    old = p.history["corner-bakery"]
    assert len(old) == 1 and old[0]["recorded"] == "2026-05-03" and old[0]["kind"] == "being built"   # kept whole
    assert p.cards["corner-bakery"]["recorded"] == "2026-11-12"
    assert p.cards["corner-bakery"]["fingerprint"].startswith("sha256:")
    gone = {(x["what"], x["text"]): (x["last_seen"], x["gone_since"]) for x in changes.left(p, "corner-bakery")}
    assert gone == {("idea", "a Friday bread box for the school"): ("2026-05-03", "2026-11-12"),
                    ("need", "a delivery driver | no | nobody yet"): ("2026-05-03", "2026-11-12"),
                    ("open decision", "open on Saturdays or not"): ("2026-05-03", "2026-11-12")}
    # "sell flour by the kilo" was reworded, not dropped, so it is not counted as gone

    assert main(["picture", "--file", pic, "changes"]) == 0
    md = capsys.readouterr().out
    assert "1 of your 1 cards have older versions. Nothing is overwritten." in md
    assert "- Corner bakery, idea: a Friday bread box for the school (last seen 2026-05-03, gone since 2026-11-12)" in md
    assert "kb cannot tell whether it was done, dropped or forgotten" in md
    assert "### Corner bakery (2 versions: 2026-05-03, 2026-11-12)" in md
    assert '- kind: was "being built", now "running product"' in md and "- new, need: a weekend baker | no" in md
    assert main(["picture", "--file", pic, "changes", "corner bakery", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["by_card"]["corner-bakery"]["versions"] == 2

    b = reports.brief(p)
    left = [x for x in b if x["kind"] == "left"]
    assert left and left[0]["move"].startswith("Look again at what left Corner bakery: ")
    assert left[0]["source"] == ["Corner bakery · older version"]


def test_a_renamed_card_takes_the_old_ones_place_and_keeps_its_history(tmp_path, capsys):
    _add(tmp_path, capsys, MAY, "2026-05-03")
    pic, _ = _add(tmp_path, capsys, NOVEMBER, "2026-11-12")
    renamed = NOVEMBER.replace("name: Corner bakery\n", "name: Town bakery\nformerly: Corner bakery\n")
    pic, out = _add(tmp_path, capsys, renamed, "2026-11-20", "renamed.md")
    assert out["updated"] == ["Town bakery"] and not out["added"] and out["cards"] == 1
    assert out["changed"]["Town bakery"] == "name Corner bakery → Town bakery"
    p = Picture.load(pic)
    assert list(p.cards) == ["town-bakery"] and "corner-bakery" not in p.history
    assert [v["name"] for v in changes.versions(p, "town-bakery")] == ["Corner bakery", "Corner bakery", "Town bakery"]
    assert p.cards["town-bakery"]["formerly"] == ["Corner bakery"]
    _, again = _add(tmp_path, capsys, renamed, "2026-11-21", "renamed.md")
    assert again["unchanged"] == ["Town bakery"]                                  # the same card again changes nothing
    _, plain = _add(tmp_path, capsys, MAY.replace("Corner bakery", "Hill bakery"), "2026-11-22", "hill.md")
    assert plain["added"] == ["Hill bakery"]                                      # no formerly: line, a new card
    _, comma = _add(tmp_path, capsys, renamed.replace("name: Town bakery\nformerly: Corner bakery",
                                                     "name: Town bakery, on the square\nformerly: Town bakery"),
                    "2026-11-23", "comma.md")
    assert comma["updated"] == ["Town bakery, on the square"] and comma["cards"] == 2   # a name may hold a comma
    back = renamed.replace("name: Town bakery\nformerly: Corner bakery",
                           "name: Town bakery again\nformerly: Town bakery, on the square; Corner bakery")
    _, two = _add(tmp_path, capsys, back, "2026-11-24", "back.md")
    assert two["updated"] == ["Town bakery again"] and two["cards"] == 2


def test_what_left_reaches_the_advice_and_the_private_list_still_holds(tmp_path, capsys):
    _add(tmp_path, capsys, MAY.replace("for the school", "for Hana's school"), "2026-05-03")
    pic, _ = _add(tmp_path, capsys, NOVEMBER, "2026-11-12")
    p = Picture.load(pic)
    lines, _ = advise.evidence(p, 100_000)
    told = [ln for ln in lines if ln.source == "Corner bakery · older version"]
    assert any("no longer lists this idea: a Friday bread box for Hana's school" in ln.text for ln in told)
    keep, held = advise.hold(advise._rows(p, None, None), Private(["Hana"]))
    assert not any("Hana" in r[0] for r in keep) and held == {"your private list": 1}


def test_a_changed_file_and_two_cards_that_disagree(tmp_path, capsys):
    pic, _ = _add(tmp_path, capsys, MAY, "2026-05-03")
    (tmp_path / "bakery.md").write_text(MAY + "\n", encoding="utf-8")                  # edited, not added again
    p = Picture.load(pic)
    assert changes.stale(p) == [{"name": "Corner bakery", "origin": str(tmp_path / "bakery.md")}]
    c = check.check(p)
    assert c["current"]["file_changed"] == ["Corner bakery"]
    assert "Its file changed since it was added" in check.check_md(c)
    (tmp_path / "bakery.md").unlink()
    assert changes.stale(Picture.load(pic)) == []                                      # a cleared download is no news

    p.add(cards.parse("PROJECT CARD\nname: Corner bakery app\nkind: idea only\nlast_activity: 2026-09-01\n",
                      "app.md"))
    d = changes.differ(p)
    assert {(x["field"], x["a_says"], x["b_says"]) for x in d} == {
        ("kind", "being built", "idea only"), ("last_activity", "2026-05-02", "2026-09-01")}
    assert d[0]["a_from"] == "bakery.md" and d[0]["b_from"] == "app.md"
    md = changes.changes_md(changes.changes(p))
    assert "Both sides are shown. Neither is taken as right." in md
    assert "None of your 2 cards has an older version yet" in md


def test_an_old_picture_without_history_loads_and_saves_as_before(tmp_path):
    p = Picture()
    p.add(cards.parse(MAY))
    path = p.save(tmp_path / "picture.json")
    assert "history" not in json.loads(path.read_text(encoding="utf-8"))
    again = Picture.load(path)
    older = {k: v for k, v in again.cards["corner-bakery"].items() if k != "owner"}       # read before owner: existed
    assert again.add([older])["unchanged"] == ["Corner bakery"] and not again.history
    again.add(cards.parse(NOVEMBER))
    assert again.history["corner-bakery"][0].get("recorded") is None
    gone = changes.left(again, "corner-bakery")
    assert gone and all(x["last_seen"] == changes.NOT_KNOWN for x in gone)
    assert "history" in json.loads(again.save(tmp_path / "picture.json").read_text(encoding="utf-8"))
