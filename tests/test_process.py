"""Layer 2, work processes from plain speech: reading each person's words, joining the hand-offs, the join types,
decision tables, checks, the what-if, the graph that kb walk reads, and the command line.

The three notes in tests/fixtures/process are invented. They stand in for real voice notes until there are some."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledgebreeder import process as P
from knowledgebreeder.cli import main
from knowledgebreeder.graph import PlantGraph
from knowledgebreeder.process.join import find
from knowledgebreeder.use import manipulation
from knowledgebreeder.walk import build

NOTES = Path(__file__).parent / "fixtures" / "process"


@pytest.fixture()
def pr():
    return P.join(P.read_all([NOTES]))


def _pipe(pr, thing, target_tag):
    return next(p for p in pr.pipes if p.thing == thing and pr.nodes[p.target].tag == target_tag)


# ------------------------------------------------------------------ reading what one person said

@pytest.mark.parametrize("said, kind, thing, who", [
    ("I get the order from the customer.", "get", "the order", "the customer"),
    ("I send it to Karim for approval.", "send", "it", "Karim"),
    ("Then I hand over the boxes to the driver", "send", "the boxes", "the driver"),
    ("I check the order is complete.", "check", "the order is complete", ""),
    ("I bake the bread.", "step", "", ""),
    ("أستلم الطلب من الزبون.", "get", "الطلب", "الزبون"),
    ("أرسل الطلب إلى كريم", "send", "الطلب", "كريم"),
    ("أتحقق من اكتمال الطلب", "check", "اكتمال الطلب", ""),
])
def test_one_sentence(said, kind, thing, who):
    s = P.parse_sentence(said)
    assert (s.kind, s.thing, s.who) == (kind, thing, who)


@pytest.mark.parametrize("said, join", [
    ("I wait for all of: the dough from the bakery, the filling from the cold room", "all"),
    ("I need any of the deposit from the customer or a letter from the bank", "any"),
    ("I wait for one of: a call from Mona; an email from Karim", "one"),
    ("أنتظر كل من: الطلب من منى، العربون من الزبون", "all"),
    ("أنتظر أي من: الطلب من منى، الطلب من كريم", "any"),
    ("أنتظر واحد من: الطلب من منى، الطلب من كريم", "one"),
])
def test_join_words(said, join):
    s = P.parse_sentence(said)
    assert s.kind == "wait" and s.join == join
    assert len(s.items) == 2 and all(t and w for t, w in s.items)


def test_if_and_otherwise_hold_what_is_done():
    s = P.parse_sentence("If the order is over 50 boxes, I send it to Karim.")
    assert s.kind == "if" and s.cond == "the order is over 50 boxes"
    assert (s.then.kind, s.then.who) == ("send", "Karim")
    e = P.parse_sentence("Otherwise I send it to the kitchen.")
    assert e.kind == "else" and e.then.who == "the kitchen"
    a = P.parse_sentence("إذا كان الطلب كبيرا، أرسل الطلب إلى كريم")
    assert a.kind == "if" and a.then.who == "كريم"


def test_header_lines_and_nothing_lost():
    p = P.read_text("person: Mona\njob: order desk\nalso: the desk, orders\n\nI sing while I work. I get flour from Sami.")
    assert (p.name, p.job, p.also) == ("Mona", "order desk", ["the desk", "orders"])
    assert [s.kind for s in p.sentences] == ["step", "get"]
    assert p.sentences[0].text == "I sing while I work"          # a sentence kb cannot place is kept as said
    assert P.read_text("I bake.", name="sami").name == "sami"   # no header: the file's name


def test_two_files_for_one_name_are_both_kept():
    pr = P.join([P.read_text("person: Mona\nI bake."), P.read_text("person: Mona\nI sell.")])
    assert sorted(p.name for p in pr.people) == ["Mona", "Mona (2)"]
    assert len([n for n in pr.nodes.values() if n.type == "Equipment"]) == 2


def test_missing_notes_are_named(tmp_path):
    with pytest.raises(FileNotFoundError):
        P.read_all([tmp_path / "nothing-here"])


# ------------------------------------------------------------------ joining the hand-offs

def test_hand_offs_said_by_both_sides_and_by_one(pr):
    both = _pipe(pr, "big orders", "Karim 1")
    assert pr.nodes[both.source].tag == "Mona 3" and both.said_by == ["Mona", "Karim"]
    assert _pipe(pr, "the order", "Sami 1").said_by in (["Mona", "Sami"], ["Karim"])
    one_side = [q for q in pr.questions if q["kind"] == "one_side"]
    assert one_side == [{"kind": "one_side", "said_by": "Karim", "thing": "the order", "other": "Sami",
                         "said": "I pass the order to the kitchen", "dir": "send"}]


def test_a_job_name_finds_the_person(pr):
    # Mona says "the kitchen"; Sami's job is kitchen, so the order reaches Sami and not an outside party
    to_sami = [p for p in pr.pipes if pr.nodes[p.source].tag == "Mona 4"]
    assert len(to_sami) == 1 and pr.nodes[to_sami[0].target].person == "Sami"


def test_outside_parties_are_sources_and_sinks(pr):
    outside = {n.name: n.attrs["direction"] for n in pr.nodes.values() if n.type == "Boundary"}
    assert outside == {"the customer": "source", "the bank": "source", "the mill": "source", "the driver": "sink"}


def test_join_types_are_kept(pr):
    joins = {pr.nodes[n].tag: g.join for n, gs in pr.needs.items() for g in gs if len(g.inputs) > 1}
    assert joins["Karim 4"] == "any" and joins["Sami 1"] == "all"


def test_an_unstated_join_is_a_question(pr):
    q = next(q for q in pr.questions if q["kind"] == "join")
    assert q["step"] == "Sami 1" and set(q["inputs"]) == {"Mona", "the mill", "Karim"}
    assert "all of them, any of them, or one of them" in P.question_text(q)


def test_decision_tables(pr):
    tables = {d.person: d.rows for d in pr.decisions}
    assert tables["Mona"] == [("the order is over 50 boxes", "Mona 3: send it to Karim for approval"),
                              ("", "Mona 4: send it to the kitchen")]
    assert [c for c, _ in tables["Karim"]] == ["the customer has paid before"]
    assert {"kind": "no_otherwise", "person": "Karim", "conds": ["the customer has paid before"]} in pr.questions
    assert not any(q["kind"] == "no_otherwise" and q["person"] == "Mona" for q in pr.questions)


def test_checks_sit_on_a_step_and_unchecked_arrivals_are_asked(pr):
    on = {pr.nodes[c].name: pr.nodes[s].tag for c, s in pr.checks}
    assert on == {"the order is complete": "Mona 1", "the price": "Karim 1", "the boxes": "Sami 2"}
    unchecked = {q["thing"] for q in pr.questions if q["kind"] == "unchecked"}
    assert unchecked == {"the deposit", "a letter of credit"}


def test_a_wait_without_from_is_joined_and_said():
    a = P.read_text("person: Mona\nI send the flour to Sami.")
    b = P.read_text("person: Sami\nI wait for all of: the flour, the eggs from the farm.")
    pr = P.join([a, b])
    assert any(q["kind"] == "unsaid_from" and q["guess"] == "Mona" for q in pr.questions)
    assert not any(q["kind"] == "one_side" for q in pr.questions)


# ------------------------------------------------------------------ what if

def test_any_of_keeps_going_when_one_input_stops(pr):
    r = P.whatif(pr, "the bank")
    assert r["also_stop"] == [] and r["kept_going_by_another_input"] == [pr.label("STEP:karim:4")]


def test_all_of_stops_when_one_input_stops(pr):
    r = P.whatif(pr, "the mill")
    assert {"Sami 1", "Sami 2", "Sami 3"} <= {x.split(":")[0] for x in r["also_stop"]}
    assert r["outside_left_waiting"] == ["the driver"] and r["checks_lost"] == ["Sami ✓1"]


def test_a_person_stopping_stops_their_steps_and_what_needs_them(pr):
    r = P.whatif(pr, "the boss")                 # Karim, by another name he goes by
    assert r["people_hit"] == ["Sami"]
    assert not any(x.startswith("Mona") for x in r["also_stop"])
    with pytest.raises(KeyError):
        P.whatif(pr, "nobody")


def test_both_inputs_of_any_of_stopping_stops_it():
    a = P.read_text("person: Lina\nI wait for any of: a call from Mona, an email from Karim.\nI book the van.")
    pr = P.join([a])
    assert pr.label("STEP:lina:2") not in P.whatif(pr, "Mona")["also_stop"]
    both = find(pr, "Mona") | find(pr, "Karim")
    assert P.stops(pr, both) >= {"STEP:lina:1", "STEP:lina:2"}


# ------------------------------------------------------------------ out again: the graph and the report

def test_the_graph_reads_as_a_plant(pr):
    g = P.to_graph(pr)
    pg = PlantGraph(g)
    assert pg.type_counts()["Equipment"] == 9
    one_side = [e for e in g["edges"] if (e["attributes"] or {}).get("flow_direction") == "inferred"]
    assert one_side and all(e["confidence"] < 0.7 for e in one_side)
    assert {t["person"] for t in g["decision_tables"]} == {"Mona", "Karim"}
    assert len(g["issues"]) == len(pr.questions)
    lost = manipulation.fail(pg, "Mona 1")["loses_supply"]["equipment"]
    assert "Karim 1" in lost
    page = build(pg)
    assert "Sami 1" in page and "the driver" in page


def test_report_in_both_languages(pr):
    en, ar = P.to_markdown(pr), P.to_markdown(pr, "ar")
    for head in ("Hand-offs (pipes)", "Decision tables (valves)", "Checks (instruments)", "Questions worth asking"):
        assert head in en
    assert "جداول القرار" in ar and "أسئلة تستحق الطرح" in ar
    assert "any of" in en and "أي من" in ar
    assert set(P.LABELS["en"]) == set(P.LABELS["ar"])
    for q in pr.questions:
        assert P.question_text(q, "ar")


def test_arabic_notes_join():
    a = P.read_text("الاسم: منى\nأستلم الطلب من الزبون.\nإذا كان الطلب كبيرا، أرسل الطلب إلى كريم.\n"
                    "وإلا أرسل الطلب إلى المطبخ.")
    b = P.read_text("الاسم: كريم\nأنتظر كل من: الطلب من منى، العربون من الزبون.")
    pr = P.join([a, b])
    p = next(p for p in pr.pipes if pr.nodes[p.target].person == "كريم" and p.thing == "الطلب")
    assert p.said_by == ["منى", "كريم"]
    assert [c for c, _ in pr.decisions[0].rows] == ["كان الطلب كبيرا", ""]


# ------------------------------------------------------------------ the command line

def test_cli(tmp_path, capsys):
    assert main(["process", "show", str(NOTES)]) == 0
    assert "Decision tables (valves)" in capsys.readouterr().out
    assert main(["process", "show", str(NOTES), "--lang", "ar"]) == 0
    assert "التسليمات" in capsys.readouterr().out
    out = tmp_path / "p" / "graph.json"
    assert main(["process", "graph", str(NOTES), "--out", str(out)]) == 0
    assert "kb walk" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["generator"] == "kb process"
    assert main(["walk", str(out), "--out", str(tmp_path / "w.html")]) == 0
    capsys.readouterr()
    assert main(["process", "whatif", str(NOTES), "--stop", "the bank"]) == 0
    assert json.loads(capsys.readouterr().out)["kept_going_by_another_input"]
    assert main(["process", "whatif", str(NOTES), "--stop", "nobody"]) == 2
    assert main(["process", "show", str(tmp_path / "missing")]) == 2
