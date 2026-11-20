"""Advice held to the cards, the scout held to its sources, and the run log that keeps which model was picked.

No model is behind these tests. A stand-in server answers what each test tells it to, so they prove what kb does
with an answer, good or bad. They say nothing about how good a real model's advice is.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from knowledgebreeder import models, scout
from knowledgebreeder.cli import main
from knowledgebreeder.models import client
from knowledgebreeder.models.config import Model
from knowledgebreeder.picture import Picture, advise
from knowledgebreeder.runlog import RunLog, query

from standin import StandIn

FIX = Path(__file__).parent / "fixtures"
CARDS, SOURCES = FIX / "demo_cards.md", FIX / "sources"
TODAY = date(2026, 11, 20)


@pytest.fixture()
def pic():
    return Picture.load(CARDS)


def _eid(user: str, needle: str) -> str:
    """The id of the first evidence line that holds these words."""
    return next(ln.split(" ", 1)[0] for ln in user.splitlines() if re.match(r"E\d+ ", ln) and needle in ln)


def _pid(user: str, name: str) -> str:
    return next(ln.split(" ", 1)[0] for ln in user.splitlines() if re.match(r"P\d+ ", ln) and name in ln)


def adviser(model, system, user):
    """Four pieces: one sound, one with an invented figure and a line that was never sent, one that cites
    nothing, one that is not advice at all."""
    part, need = _eid(user, "customer list with phone numbers"), _eid(user, "a list of past customers")
    return "Here you go:\n" + json.dumps({"advice": [
        {"move": "Send the bakery's customer list to the Saturday class.", "why": "The class needs past customers.",
         "cites": [part, f"[{need.lower()}]"], "first_step": "Export the list tonight.", "kind": "join"},
        {"move": "Invite all 300 customers by Friday.", "why": "They are waiting.", "cites": [need, "E999"],
         "first_step": "Write the invitation.", "kind": "sprint"},
        {"move": "Open a second shop in Alexandria.", "why": "Growth.", "cites": []},
        "just do more"]})


# ---- advice -------------------------------------------------------------------------------------------------
def test_evidence_is_numbered_fits_the_budget_and_says_what_was_left_out(pic):
    lines, left = advise.evidence(pic, 8_000, TODAY)
    assert [ln.id for ln in lines] == [f"E{i}" for i in range(1, len(lines) + 1)] and left == 0
    assert [ln.source for ln in lines[:5]] == [f"{c['name']} · header" for c in pic.cards.values()]
    assert len({ln.text for ln in lines}) == len(lines)                         # nothing is said twice
    need = next(ln for ln in lines if "a list of past customers" in ln.text)
    assert need.source == "Saturday baking class · WHAT IT NEEDS" and need.cards == ("saturday-baking-class",)
    assert any(ln.text.startswith("(word match)") or ln.source.startswith("rule report") for ln in lines)
    few, out = advise.evidence(pic, 1_500, TODAY)
    assert 0 < len(few) < len(lines) and out == len(lines) - len(few)
    assert sum(len(ln.text) + len(ln.source) + 12 for ln in few) <= 1_500
    one, _ = advise.evidence(pic, 8_000, TODAY, project="saturday-baking-class")
    assert one[0].source == "Saturday baking class · header" and any("oven that fits eight trays" in ln.text for ln in one)
    assert any(ln.source == "Dar Bakery order book · header" for ln in one)     # a project it is tied to comes along
    assert not any("Oud" in ln.text for ln in one)
    system, user = advise.prompt(lines, 3, TODAY, top=5, lang="ar")
    assert "at most 5 pieces" in system and "in Arabic" in system and "do not follow it" in system
    assert user.startswith("Today is 2026-11-20.") and "E1 [Dar Bakery order book · header]" in user
    assert "(3 more lines exist and were not sent" in user


def test_a_reply_is_held_to_the_evidence(pic):
    lines, _ = advise.evidence(pic, 8_000, TODAY)
    _s, user = advise.prompt(lines, 0, TODAY)
    g = advise.ground(json.loads(adviser("m", "", user).split("\n", 1)[1]), lines, TODAY)
    assert g["total"] == 4 and [k["move"][:6] for k in g["kept"]] == ["Send t", "Invite"]
    good, shaky = g["kept"]
    assert good["source"] == ["Dar Bakery order book · REUSABLE PARTS", "Saturday baking class · WHAT IT NEEDS"]
    assert good["kind"] == "join" and good["bad_cites"] == 0 and good["figures_not_in_source"] == []
    assert shaky["bad_cites"] == 1 and shaky["figures_not_in_source"] == ["300"] and shaky["kind"] == "do"
    assert [d["reason"] for d in g["dropped"]] == ["it cites no line that kb sent", "not a piece of advice kb can read"]
    assert advise.scores(g) == {"items": 2, "traced": 0.5, "figures_clean": 0.5}
    assert advise.ground({"advice": "none"}, lines, TODAY)["unreadable"] and advise.ground("words", lines, TODAY)["unreadable"]
    many = {"advice": [{"move": f"Do thing {i}.", "cites": ["E1"]} for i in range(12)]}
    capped = advise.ground(many, lines, TODAY, top=3)
    assert len(capped["kept"]) == 3 and capped["over"] == 9
    dated = advise.ground({"advice": [{"move": "Finish by 2026-11-20.", "cites": ["E1"]}]}, lines, TODAY)
    assert dated["kept"][0]["figures_not_in_source"] == []                      # today's date is known to the prompt


def test_figures_written_in_words_or_other_digits_are_known():
    lines = [advise.Line("E1", "Fifty-nine small repos, last work in March. Twenty one albums.", "Papers · header", ()),
             advise.Line("E2", "١٣٨ عملا منشورا", "AIRED · header", ())]
    said = lambda move, cite: advise.ground({"advice": [{"move": move, "cites": [cite]}]}, lines, TODAY)["kept"][0]
    assert said("Archive the 59 repos.", "E1")["figures_not_in_source"] == []
    assert said("Keep the 21 albums.", "E1")["figures_not_in_source"] == []
    assert said("Archive the 60 repos.", "E1")["figures_not_in_source"] == ["60"]
    assert said("Count the 138 works.", "E2")["figures_not_in_source"] == []
    assert said("Count the ١٣٩ works.", "E2")["figures_not_in_source"] == ["139"]
    assert said("Take one small step.", "E2")["figures_not_in_source"] == []   # a word in the answer is not a figure


def test_advice_from_a_local_model(pic):
    with StandIn(adviser) as sv:
        m = Model("local", "openai", sv.url + "/v1", "small")
        r = advise.advise(pic, m, today=TODAY)
        assert r["where"] == models.HERE and r["scores"]["traced"] == 0.5 and len(r["advice"]) == 2
        text = advise.advice_md(r)
        assert "Written by local (small) on this machine" in text and "A model wrote this." in text and "You sign." in text
        assert "From: Dar Bakery order book · REUSABLE PARTS; Saturday baking class · WHAT IT NEEDS" in text
        assert "Check: 300 is in none of the lines it cites." in text
        assert "Not shown: 2 of 4 pieces cited no line that kb sent." in text and "Alexandria" not in text
        sent = sv.posts()[0]["body"]["messages"][1]["content"]
        assert "Dar Bakery order book" in sent and len(sent) < 9_500           # the budget holds
        one = advise.advise(pic, m, today=TODAY, project="saturday-baking-class")
        assert one["project"] == "Saturday baking class" and "# Advice about Saturday baking class" in advise.advice_md(one)
        assert "asks about one project: Saturday baking class" in sv.posts()[1]["body"]["messages"][1]["content"]


def _setup(tmp_path, sv, monkeypatch=None, far=False):
    """A picture, a models file with two local models (and one made to look far away), and paths for the rest."""
    w = tmp_path / "w"
    w.mkdir()
    pic = str(w / "picture.json")
    assert main(["picture", "--file", pic, "add", str(CARDS)]) == 0
    book = {"default": "small", "models": {
        "small": {"url": sv.url + "/v1", "model": "small"}, "big": {"url": sv.url + "/v1", "model": "big"},
        "far": {"url": sv.url + "/far/v1", "model": "small"}}}
    (w / "models.json").write_text(json.dumps(book), encoding="utf-8")
    if far:
        real = client.place
        monkeypatch.setattr(client, "place", lambda url: ("far.example", models.OUTSIDE) if "/far/" in url else real(url))
    return pic, str(w / "models.json"), str(w / "runs.db"), str(w / "scout.jsonl")


def test_advise_command_refuses_shows_and_records(tmp_path, capsys, monkeypatch):
    with StandIn(adviser) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv, monkeypatch, far=True)
        base = ["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db, "--today", "2026-11-20"]
        capsys.readouterr()
        assert main(base + ["--models", "small,far"]) == 3                      # one refusal stops the whole run
        err = capsys.readouterr().err
        assert err.startswith("Nothing was sent.") and "far.example" in err and "--allow far" in err
        assert sv.seen == [] and not Path(db).exists()

        assert main(base + ["--model", "far", "--show-prompt"]) == 0            # looking is always allowed
        out = capsys.readouterr().out
        assert "Nothing was sent." in out and "Evidence:\nE1 [" in out and sv.seen == []

        assert main(base + ["--models", "small,far,big", "--allow", "far"]) == 0
        out = capsys.readouterr().out
        assert out.count("# Advice") == 3 and "Written by far (small) on outside" in out
        run_id = re.search(r"kb models pick (run_\w+) NAME", out).group(1)
        log = RunLog(db)
        run = query.show(log, run_id, payloads=True)
        assert run["task"] == "advise" and run["subject"] == "whole picture" and run["status"] == "ok"
        assert [(s["worker"], s["version"], s["scores"]["traced"]) for s in run["steps"]] == [
            ("small", "small", 0.5), ("far", "small", 0.5), ("big", "big", 0.5)]
        assert run["steps"][0]["input"]["evidence"][0]["id"] == "E1" and len(run["steps"][0]["output"]["advice"]) == 2
        log.close()

        assert main(["models", "--file", mfile, "pick", run_id, "big", "--db", db]) == 0
        assert "big was picked over small, far" in capsys.readouterr().out
        assert main(["models", "--file", mfile, "pick", run_id, "small", "--db", db]) == 2
        assert "already recorded" in capsys.readouterr().err
        assert main(["models", "--file", mfile, "pick", run_id, "nobody", "--db", db]) == 2
        capsys.readouterr()
        log = RunLog(db)
        board = query.workers(log, task="advise", score="picked")
        assert [(w["worker"], w["version"], w["scores"]["picked"]) for w in board] == [
            ("big", "big", 1.0), ("far", "small", 0.0), ("small", "small", 0.0)]
        log.close()

        assert main(base + ["--project", "the oven that never was"]) == 2
        assert "does not name one project" in capsys.readouterr().err
        assert main(base + ["--project", "Saturday baking class", "--json", "--no-log"]) == 0
        got = json.loads(capsys.readouterr().out)
        assert got["run"] is None and got["results"][0]["project"] == "Saturday baking class"


def test_a_model_that_fails_is_recorded_as_failed(tmp_path, capsys):
    with StandIn(lambda m, s, u: 500 if m == "big" else adviser(m, s, u)) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv)
        base = ["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db, "--today", "2026-11-20"]
        assert main(base + ["--models", "small,big"]) == 0
        assert "big (big) gave nothing" in capsys.readouterr().out
        log = RunLog(db)
        steps = query.show(log, query.runs(log)[0]["id"])["steps"]
        assert [(s["worker"], s["status"]) for s in steps] == [("small", "ok"), ("big", "failed")]
        log.close()
        assert main(base + ["--model", "big"]) == 2                              # nobody answered


# ---- the scout ----------------------------------------------------------------------------------------------
def reader(model, system, user):
    """Says yes to the fund (and names a project that was never offered), yes to the oud evening, makes up a
    chance from the note, and passes over the advert."""
    if "Food Makers Fund" in user:
        return json.dumps({"opportunity": True, "what": "A fund that pays toward a delivery vehicle.",
                           "for": [_pid(user, "Dar Bakery order book"), "P99"], "why": "The order book needs a driver.",
                           "quote": "up to 40,000 EGP toward one piece of equipment  or one delivery vehicle",
                           "deadline": "2026-12-15", "deadline_quote": "Applications close on 15 December 2026",
                           "next_step": "Write the two pages."})
    if "بيت المقام" in user:
        return json.dumps({"opportunity": True, "what": "تسجيل شهري مجاني لعازفي العود", "for": [_pid(user, "Oud practice log")],
                           "why": "It matches the idea of recording one piece a month.", "quote": "تسجيل مقطوعة واحدة كل شهر",
                           "deadline": "2027-01-05", "deadline_quote": "آخر موعد للتقديم 5 يناير 2027",
                           "next_step": "Pick the piece."}, ensure_ascii=False)
    if "Weekend sale" in user:
        return json.dumps({"opportunity": False, "reason": "An advert with nothing to act on."})
    return json.dumps({"opportunity": True, "what": "A grant for everyone.", "for": ["P1"],
                       "quote": "a grant of one million for every baker", "deadline": "2026-12-01", "deadline_quote": "soon"})


def test_sources_are_read_as_plain_words(pic, tmp_path):
    files = scout.sources([SOURCES])
    assert [f.name for f in files] == ["cairo-food-makers-fund.md", "oud-evening.txt", "phone-sale.html"]   # not the note
    assert scout.sources([SOURCES, files[0]]) == files
    with pytest.raises(KeyError):
        scout.sources([tmp_path / "nowhere"])
    page = scout.read_source(SOURCES / "phone-sale.html")
    assert page.startswith("Weekend sale") and "Corner Phones & More" in page
    assert "grant" not in page and "color" not in page and "<" not in page       # scripts, styles and tags are gone
    fund = scout.read_source(files[0])
    assert [m["name"] for m in scout.match(pic, fund)][:2] == ["Dar Bakery order book", "Dar Bakery stock sheet"]
    assert "delivery" in scout.match(pic, fund)[0]["shared"] and scout.match(pic, page) == []


def test_a_long_source_keeps_its_opening_and_what_is_closest(pic):
    filler = "\n\n".join(f"Paragraph {i} about the weather in a town far away and nothing else at all." for i in range(200))
    text = "The long newsletter\n\n" + filler + "\n\nBakeries can apply for a delivery vehicle for every order. Applications close on 3 March 2027.\n\n" + filler
    vocabulary = {w for c in pic.cards.values() for w in scout.scout._card_words(c)}
    cut, was_cut = scout.excerpt(text, vocabulary, 2_000)
    assert was_cut and len(cut) <= 2_300 and cut.startswith("The long newsletter") and "3 March 2027" in cut and "[...]" in cut
    assert scout.excerpt("short", vocabulary, 2_000) == ("short", False)
    _s, user, offered, facts = scout.prompt(pic, text, scout.match(pic, text), TODAY, budget=4_000)
    assert facts["cut"] and facts["total_chars"] == len(text) and "parts of it" in user and len(offered) == 5
    assert user.index("P1 Dar Bakery order book") < user.index("<<<") and "Wants: a delivery driver" in user


def test_an_answer_is_held_to_the_source():
    text = scout.read_source(SOURCES / "cairo-food-makers-fund.md")
    offered = {"P1": "dar-bakery-order-book", "P2": "oud-practice-log"}
    yes = {"opportunity": True, "what": "A fund.", "for": ["p1"], "why": "w", "next_step": "n",
           "quote": "“up to 40,000 EGP toward one piece of equipment”", "deadline": "2026-12-15",
           "deadline_quote": "applications close on 15 December 2026"}
    ok = scout.check(yes, text, offered, TODAY)
    assert ok["verdict"] == "opportunity" and ok["for_ids"] == ["dar-bakery-order-book"] and ok["deadline"] == "2026-12-15"
    assert ok["notes"] == [] and ok["quote"] == "up to 40,000 EGP toward one piece of equipment"
    assert scout.check(yes, text, offered, date(2026, 12, 16))["verdict"] == "closed"
    for change, note in (({"quote": "up to 90,000 EGP toward anything you like"}, "not in the text word for word"),
                         ({"quote": "the Fund"}, "not in the text word for word"),       # too short to show anything
                         ({"quote": ""}, "gave no quote"), ({"for": ["P7"]}, "names no project of yours"),
                         ({"for": "P1"}, "names no project of yours")):
        bad = scout.check({**yes, **change}, text, offered, TODAY)
        assert bad["verdict"] == "unchecked" and any(note in n for n in bad["notes"]), change
    for change in ({"deadline": "2026-12-25"}, {"deadline": "2027-12-15"}, {"deadline_quote": "closes on 15 December 2026 sharp"},
                   {"deadline_quote": "Late applications are not read"}, {"deadline": "mid December"}):
        late = scout.check({**yes, **change}, text, offered, TODAY)
        assert late["verdict"] == "opportunity" and late["deadline"] is None and "could not be confirmed" in late["notes"][0]
    half = scout.check({**yes, "for": ["P1", "P9"]}, text, offered, TODAY)
    assert half["verdict"] == "opportunity" and "left out" in half["notes"][0]
    assert scout.check({"opportunity": False, "reason": "News."}, text, offered, TODAY) == {
        "verdict": "passed", "reason": "News.", "notes": []}
    assert scout.check({"opportunity": "yes"}, text, offered, TODAY)["verdict"] == "error"
    assert scout.check(["yes"], text, offered, TODAY)["verdict"] == "error"
    arabic = scout.read_source(SOURCES / "oud-evening.txt")
    ar = scout.check({"opportunity": True, "for": ["P2"], "quote": "تسجيل مقطوعة واحدة كل شهر", "deadline": "2027-01-05",
                      "deadline_quote": "آخر موعد للتقديم ٥ يناير ٢٠٢٧".replace("٥", "5").replace("٢٠٢٧", "2027")}, arabic, offered, TODAY)
    assert ar["verdict"] == "opportunity" and ar["deadline"] == "2027-01-05"


def test_the_scout_reads_checks_and_keeps_a_ledger(pic, tmp_path):
    (tmp_path / "s").mkdir()
    for f in scout.sources([SOURCES]):
        (tmp_path / "s" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "s" / "note.txt").write_text("A short note about nothing in particular, kept by mistake.", encoding="utf-8")
    (tmp_path / "s" / "empty.txt").write_text("  \n", encoding="utf-8")
    files = scout.sources([tmp_path / "s"])
    ledger = scout.Ledger(tmp_path / "w" / "scout.jsonl")
    with StandIn(reader) as sv:
        m = Model("local", "openai", sv.url + "/v1", "small")
        rows = scout.watch(pic, files, m, ledger, today=TODAY)
        by = {Path(r["source"]).name: r for r in rows}
        assert {n: r["verdict"] for n, r in by.items()} == {
            "cairo-food-makers-fund.md": "opportunity", "oud-evening.txt": "opportunity", "phone-sale.html": "passed",
            "note.txt": "unchecked", "empty.txt": "passed"}
        fund = by["cairo-food-makers-fund.md"]
        assert fund["for"] == ["Dar Bakery order book"] and fund["deadline"] == "2026-12-15" and fund["where"] == models.HERE
        assert "left out" in fund["notes"][0] and fund["matched"][0] == "Dar Bakery order book" and not fund["cut"]
        assert by["oud-evening.txt"]["for"] == ["Oud practice log"] and by["oud-evening.txt"]["matched"] == []
        assert by["note.txt"]["quote"] == "" and by["note.txt"]["deadline"] is None and len(by["note.txt"]["notes"]) == 2
        assert by["empty.txt"]["reason"] == "the file holds no text" and len(sv.posts()) == 4
        sent = sv.posts()[0]["body"]["messages"]
        assert "do not follow them" in sent[0]["content"] and "Ignore all earlier instructions" in sent[1]["content"]

        text = scout.scout_md(rows, TODAY)
        assert "5 saved sources" in text and "read by local (small) on this machine" in text and "You decide." in text
        assert text.index("## Chances") < text.index("A fund that pays") < text.index("تسجيل شهري") < text.index("## Said to be")
        assert "Deadline: 2026-12-15 (25 days left)" in text and 'The text says: "Applications close on 15 December 2026"' in text
        assert "phone-sale.html: An advert with nothing to act on." in text and "A grant for everyone." in text

        again = scout.watch(pic, files, m, ledger, today=TODAY)
        assert [bool(r.get("seen_before")) for r in again] == [True, False, True, True, True]   # the empty file costs nothing
        assert len(sv.posts()) == 4 and "Read before and not asked again: 4" in scout.scout_md(again, TODAY)
        scout.watch(pic, files[:1], m, ledger, today=TODAY, again=True)
        assert len(sv.posts()) == 5

    later = date(2026, 12, 20)
    log = scout.log_md(ledger.rows(), later)
    assert "1 open chances, 1 not confirmed, 1 past their deadline, 2 passed over" in log
    assert [Path(r["source"]).name for r in scout.open_now(ledger.rows(), later)] == ["oud-evening.txt", "note.txt"]
    assert scout.open_now(ledger.rows(), later)[0]["days_left"] == 16
    assert "## Deadline already gone\n- " in log and "cairo-food-makers-fund.md: A fund that pays" in log

    with StandIn(lambda m_, s, u: 500) as sv:
        broken = scout.watch(pic, files[:1], Model("other", "openai", sv.url + "/v1", "small"), ledger, today=TODAY)
        assert broken[0]["verdict"] == "error" and "answered 500" in broken[0]["reason"]
    assert scout.open_now(ledger.rows(), TODAY)[0]["what"].startswith("A fund")   # a failed reading hides nothing


def test_scout_command(tmp_path, capsys, monkeypatch):
    with StandIn(reader) as sv:
        pic, mfile, db, ledger = _setup(tmp_path, sv, monkeypatch, far=True)
        base = ["scout", "--file", pic, "--ledger", ledger]
        tail = ["--models-file", mfile, "--runlog", db, "--today", "2026-11-20"]
        capsys.readouterr()
        assert main(base + ["read", str(SOURCES), "--model", "far"] + tail) == 3
        err = capsys.readouterr().err
        assert "Nothing was sent." in err and "3 saved sources" in err and "--allow far" in err
        assert sv.seen == [] and not Path(ledger).exists() and not Path(db).exists()

        assert main(base + ["read", str(SOURCES)] + tail) == 0
        out = capsys.readouterr().out
        assert "## Chances\n1. A fund that pays toward a delivery vehicle." in out and "kb scout log" in out
        log = RunLog(db)
        run = query.show(log, query.runs(log, task="scout")[0]["id"])
        assert [(s["subject"], s["scores"]) for s in run["steps"]] == [
            ("cairo-food-makers-fund.md", {"said_chance": 1.0, "confirmed": 1.0}),
            ("oud-evening.txt", {"said_chance": 1.0, "confirmed": 1.0}),
            ("phone-sale.html", {"said_chance": 0.0, "confirmed": 0.0})]
        log.close()
        assert main(base + ["log", "--today", "2026-11-20"]) == 0
        assert "3 sources read so far" in capsys.readouterr().out
        assert main(base + ["log", "--json"]) == 0
        assert len(json.loads(capsys.readouterr().out)["rows"]) == 3
        assert main(base + ["read", str(tmp_path / "none")] + tail) == 2
