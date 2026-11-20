"""Walk the plant: where items stand, the what-if answers behind the page, the page itself and the command line."""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from importlib import resources
from pathlib import Path

import pytest

from knowledgebreeder.cli import main
from knowledgebreeder.graph import PlantGraph
from knowledgebreeder.use import manipulation
from knowledgebreeder.walk import build, sketch
from knowledgebreeder.walk.labels import LABELS

FIX = Path(__file__).parent / "fixtures" / "demo_graph.json"
TODAY = date(2026, 11, 20)
MAIN = ["BOUNDARY:RAW WATER", "V-001", "TK-101", "V-002", "P-101", "P01.L3.1", "CV-0502", "FE-0502", "TK-102",
        "V-003", "BOUNDARY:TO PROCESS"]


@pytest.fixture()
def pg():
    return PlantGraph.load(FIX)


def _data(page: str) -> dict:
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


def _key(data: dict, name: str) -> str:
    return next(k for k, n in data["nodes"].items() if n["name"] == name)


def _plant(nodes, edges):
    """A small plant in the graph.json format. nodes: (id, type, kind), edges: (source, target)."""
    return PlantGraph({"plant": {"name": "T"}, "nodes": [
        {"id": i, "type": t, "label": i, "tag": i, "kind": k, "sheets": [], "confidence": 0.9, "attributes": a}
        for i, t, k, a in nodes], "edges": [
        {"id": f"E{n}", "source": s, "target": t, "type": "FLOWS_TO", "attributes": {}} for n, (s, t) in enumerate(edges)]})


def test_the_line_runs_left_to_right_and_branches_drop_below(pg):
    sk = sketch(pg)
    assert [sk.col[n] for n in MAIN] == list(range(11)) and {sk.row[n] for n in MAIN} == {0}
    assert sk.col["P-102"] == sk.col["P-101"] and sk.row["P-102"] == 1          # the standby pump stands under the duty pump
    assert "P01.L2.1" not in sk.col and "P01.L3.1" in sk.col                    # bare pipe is a line, a meeting of lines is drawn
    assert sk.items[:5] == MAIN[:5] and "P-102" in sk.items and not sk.loose
    by_ends = {(ln.u, ln.v): ln for ln in sk.lines}
    assert by_ends["CV-0502", "FE-0502"].through == ["P01.L3.2"]
    assert sk.lines[sk.carrier["P01.L3.2"]] is by_ends["CV-0502", "FE-0502"]
    spare = by_ends["TK-101", "P-102"]
    assert spare.inferred and len(spare.way) == 1 and sk.row[spare.way[0]] == 1  # a bend keeps the column under V-002 free
    assert not by_ends["TK-101", "V-002"].inferred and not any(ln.back for ln in sk.lines)


def test_a_recycle_runs_back_and_loose_items_are_kept():
    pg = _plant([("IN", "Boundary", None, {"direction": "source"}), ("A", "Equipment", "tank", {}),
                 ("B", "Equipment", "reactor", {}), ("OUT", "Boundary", None, {"direction": "sink"}),
                 ("S1", "PipeSegment", None, {}), ("ALONE", "Equipment", "tank", {}),
                 ("FE-9", "Instrument", None, {"inline": True})],
                [("IN", "A"), ("A", "B"), ("B", "OUT"), ("B", "S1"), ("S1", "A")])
    sk = sketch(pg)
    assert [sk.col[n] for n in ("IN", "A", "B", "OUT")] == [0, 1, 2, 3]
    back = [ln for ln in sk.lines if ln.back]
    assert [(ln.u, ln.v, ln.through) for ln in back] == [("B", "A", ["S1"])]
    assert sk.loose == ["ALONE", "FE-9"]
    page = build(pg, today=TODAY)                                               # and the page can draw all of it
    data = _data(page)
    assert data["nodes"][_key(data, "A")]["up"] == [_key(data, "IN"), _key(data, "B")]
    assert data["nodes"][_key(data, "ALONE")]["fail"]["lost"] == [] and 'data-i18n="loose"' in page
    assert sketch(_plant([], [])).items == [] and "<svg" in build(_plant([], []), today=TODAY)


def test_one_trunk_runs_through_every_meeting_point():
    """Two sets of parallel items in a row must not push the line down a step each time."""
    eq = lambda i: (i, "Equipment", "tank", {})
    seg = lambda i: (i, "PipeSegment", None, {})
    pg = _plant([("IN", "Boundary", None, {"direction": "source"}), seg("H1"), eq("A1"), eq("B1"), seg("H2"), eq("A2"),
                 eq("B2"), eq("C2"), seg("H3"), ("OUT", "Boundary", None, {"direction": "sink"})],
                [("IN", "H1"), ("H1", "A1"), ("H1", "B1"), ("A1", "H2"), ("B1", "H2"), ("H2", "A2"), ("H2", "B2"),
                 ("H2", "C2"), ("A2", "H3"), ("B2", "H3"), ("C2", "H3"), ("H3", "OUT")])
    sk = sketch(pg)
    assert [sk.row[n] for n in ("IN", "H1", "A1", "H2", "A2", "H3", "OUT")] == [0] * 7
    assert (sk.row["B1"], sk.row["B2"], sk.row["C2"]) == (1, 1, 2) and sk.col["B2"] == sk.col["A2"] == sk.col["C2"]


def test_whatif_as_ids_says_the_same_as_whatif(pg):
    ctx = manipulation.context(pg)
    for tag in pg.of_type("Equipment", "Component", "Boundary"):
        sets, said = manipulation.fail_sets(pg, tag, ctx), manipulation.fail(pg, tag)
        assert sorted(pg.label(n) for n in sets["lost"] if pg.node(n)["type"] == "Equipment") == said["loses_supply"]["equipment"]
        assert [pg.label(n) for n in sets["blind"]] == said["instruments_blind"]
        box, told = manipulation.isolate_sets(pg, tag), manipulation.isolate(pg, tag)
        assert sorted(pg.label(v) for v in box["valves"]) == [v["tag"] for v in told["close"]]
        assert sorted(pg.label(n) for n in box["open_ends"]) == told["no_valve_before"]
    assert manipulation.isolate_sets(pg, "FIT-0502") is None                    # not on a process line
    assert manipulation.fail_sets(pg, "FIT-0502")["lost"] == set()


def test_the_page_holds_every_answer(pg):
    data = _data(build(pg, today=TODAY))
    name = lambda keys: sorted(data["nodes"][k]["name"] for k in keys)
    assert len(data["nodes"]) == 15 and data["counts"] == {"items": 12, "instruments": 4, "loops": 1, "questions": 8}
    assert [data["nodes"][k]["name"] for k in data["order"][:3]] == ["RAW WATER", "V-001", "TK-101"]
    cv = data["nodes"][_key(data, "CV-0502")]
    assert name(cv["up"]) == ["P01.L3.1"] and name(cv["down"]) == ["FE-0502"] and cv["kind"] == "control valve"
    assert name(cv["fail"]["lost"]) == ["FE-0502", "TK-102", "TO PROCESS", "V-003"] and cv["fail"]["other"] == 5
    assert name(cv["fail"]["blind"]) == ["FE-0502", "FIT-0502"] and data["loops"][cv["fail"]["loops"][0]]["name"] == "F-0502"
    assert name(data["loops"][0]["members"]) == ["CV-0502", "FE-0502", "FIC-0502", "FIT-0502"]
    assert ["fail position", "FC"] in cv["attrs"]
    p101 = data["nodes"][_key(data, "P-101")]
    assert p101["fail"]["lost"] == [] and name(p101["fail"]["spared"]) == ["TK-102", "TO PROCESS"]
    tk = data["nodes"][_key(data, "TK-102")]
    assert name(tk["iso"]["close"]) == ["V-003"] and name(tk["iso"]["open"]) == ["P-101", "P-102"]
    assert {"CV-0502", "FE-0502", "P01.L3.1"} <= set(name(tk["iso"]["inside"]))
    fit = data["nodes"][_key(data, "FIT-0502")]
    assert fit["iso"] is None and fit["c"] == -1 and name(fit["to"]) == ["FIC-0502"] and name(fit["from"]) == ["FE-0502"]
    assert fit["measures"] == [{"k": None, "name": "P01.L3.2"}]                # a stretch of pipe, not a drawn item
    low = data["nodes"][_key(data, "P-102")]
    assert low["low"] and low["conf"] == 0.6 and low["q"]
    assert [(s["tag"], s["starves"], s["sinks"]) for s in data["spof"]] == [("TK-101", 4, ["TO PROCESS"]), ("TK-102", 1, ["TO PROCESS"])]
    assert data["spof"][0]["key"] == _key(data, "TK-101")
    assert data["stats"]["sources"] == ["RAW WATER"] and data["stats"]["low"] == ["P-102"]
    asked = {q["rule"]: q["keys"] for q in data["questions"]}
    assert name(asked["parallel_set"]) == ["P-101", "P-102"]


def test_the_page_is_one_private_offline_file(pg):
    raw = copy.deepcopy(pg.data)
    raw["plant"]["name"] = 'Plant </script><script>alert(1)</script> & "quotes"'
    for n in raw["nodes"]:
        if n["id"] == "V-001":
            n["tag"] = n["label"] = '<img src=x onerror=alert(1)>'
    page = build(PlantGraph(raw), today=TODAY)
    assert page.startswith("<!doctype html>") and "default-src 'none'" in page
    assert "<script>alert(1)" not in page and "<img src=x" not in page          # plant text cannot become markup
    assert page.count("<script") == 2 and page.count("</script>") == 2
    assert not re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", page)   # nothing is fetched
    assert len(re.findall(r'<g class="n[ "]', page)) == 15 and len(re.findall(r'<g class="e[ "]', page)) == 12
    assert len(re.findall(r'<g class="n bub', page)) == 3 and len(re.findall(r'class="n k-\w+ lowc"', page)) == 1
    assert page.count('class="e inf"') == 2 and page.count('class="pick"') == 15   # three guessed edges, two drawn lines
    assert page.count('<g class="sp">') == 3 and page.count('class="qm"') >= 4  # two single points and the legend's own
    assert page.count('class="lead"') == 2 and page.count('class="sig"') == 4   # with the legend's own
    assert set(LABELS["ar"]) == set(LABELS["en"])
    assert resources.files("knowledgebreeder.walk").joinpath("plant.html").read_text(encoding="utf-8").isascii()
    arabic = build(pg, today=TODAY, lang="ar", title="محطة المياه")
    assert '<html lang="ar" dir="rtl">' in arabic and "<title>محطة المياه</title>" in arabic
    assert _data(arabic)["title"] == "محطة المياه" and build(pg, today=TODAY, lang="xx").startswith('<!doctype html>\n<html lang="en"')


def test_command_line(tmp_path, capsys):
    out = tmp_path / "out" / "plant.html"
    assert main(["walk", str(FIX), "--out", str(out), "--lang", "ar", "--title", "Demo"]) == 0
    assert "private" in capsys.readouterr().out
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and _data(page)["lang"] == "ar" and "<title>Demo</title>" in page
