"""The use layer and the scoreboard on the demo plant (see fixtures/make_demo_graph.py for its layout)."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from knowledgebreeder.cli import main
from knowledgebreeder.graph import PlantGraph
from knowledgebreeder.scoreboard import pid2graph, score as sb
from knowledgebreeder.use import manipulation, research, statistics, synthesis

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def pg():
    return PlantGraph.load(FIX / "demo_graph.json")


def test_walks(pg):
    assert pg.find("tk101") == "TK-101"
    assert "TK-102" in pg.downstream("TK-101") and "TK-101" in pg.upstream("CV-0502")
    with pytest.raises(KeyError):
        pg.find("XX-999")


def test_statistics(pg):
    s = statistics.stats(pg)
    assert s["equipment_by_kind"] == {"tank": 2, "centrifugal_pump": 2}
    assert s["topology"]["sources"] == ["BOUNDARY:RAW WATER"] and s["topology"]["sinks"] == ["BOUNDARY:TO PROCESS"]
    assert s["coverage"]["control_valves_outside_loops"] == []
    assert s["trust"]["nodes_below_0.7"] == ["P-102"]
    assert 0 < s["trust"]["inferred_flow_share"] < 0.25
    assert "Longest path" in statistics.to_markdown(s)


def test_fail(pg):
    # the control valve is on the only path to TK-102
    r = manipulation.fail(pg, "CV-0502")
    assert r["loses_supply"]["equipment"] == ["TK-102"] and r["loses_supply"]["sinks"] == ["BOUNDARY:TO PROCESS"]
    assert {"FE-0502", "FIT-0502"} <= set(r["instruments_blind"]) and r["loops_affected"] == ["F-0502"]
    # P-101 has a standby in parallel, so nothing is starved
    r = manipulation.fail(pg, "P-101")
    assert r["loses_supply"]["equipment"] == [] and "TK-102" in r["still_supplied_by_another_path"]


def test_isolate(pg):
    r = manipulation.isolate(pg, "TK-102")
    assert [v["tag"] for v in r["close"]] == ["V-003"] and not r["isolable"]   # nothing shuts it off from the pumps
    assert set(r["no_valve_before"]) == {"P-101", "P-102"}
    assert "CV-0502" in r["also_inside_the_envelope"]                        # a control valve is not an isolation valve


def test_single_points(pg):
    top = manipulation.single_points(pg)
    assert top[0]["tag"] == "TK-101" and "P-101" not in [r["tag"] for r in top]


def test_research(pg):
    qs = research.questions(pg)
    got = {(q["rule"], q["subject"]) for q in qs}
    assert ("vessel_level", "TK-102") in got and ("vessel_level", "TK-101") not in got   # LI-101 covers TK-101
    assert ("pump_discharge_pressure", "P-101") in got
    assert ("pump_isolation", "P-102") in got
    assert ("parallel_set", "P-101 / P-102") in got
    assert ("low_confidence", "P-102") in got
    assert not any(q["rule"] == "orphan_control_valve" for q in qs)
    assert [q["priority"] for q in qs] == sorted((q["priority"] for q in qs), key=["high", "medium", "low"].index)
    assert all(q["question"].endswith("?") for q in qs)


def test_synthesis(pg):
    text = synthesis.describe(pg)
    assert text.index("BOUNDARY:RAW WATER feeds") < text.index("TK-101 (tank) feeds") < text.index("TK-102 (tank) feeds")
    assert "FIC-0502 controls flow by moving CV-0502" in text and "## Open questions" in text
    card = synthesis.brief(pg, "P-101")
    assert "**Fed by:** TK-101" in card and "**Feeds:** TK-102" in card
    assert "nothing downstream loses supply" in card and "close V-002" in card
    assert "**Sits between:**" in synthesis.brief(pg, "CV-0502")


def test_score_and_promotion(pg, tmp_path):
    gold = {"tags": ["TK-101", "TK-102", "P-101", "P-102", "V-001", "V-002", "V-003", "CV-0502",
                     "FE-0502", "FIT-0502", "FIC-0502", "LI-101", "PI-101"],
            "feeds": [["TK-101", "P-101"], ["TK-101", "P-102"], ["P-101", "TK-102"], ["P-102", "TK-102"],
                      ["BOUNDARY:RAW WATER", "TK-101"], ["TK-102", "BOUNDARY:TO PROCESS"]],
            "loops": {"F-0502": ["FE-0502", "FIT-0502", "FIC-0502", "CV-0502"]}}
    res = sb.score(pg, gold)
    assert res["tags"]["missing"] == ["PI101"] and res["tags"]["precision"] == 1.0
    assert res["flow"]["f1"] == 1.0 and res["loops"] == {"recall": 1.0, "member_overlap": 1.0}
    worse = pg.copy()
    worse.g.remove_node("P-102")
    res2 = sb.score(worse, gold)
    assert res2["flow"]["f1"] < 1.0
    assert sb.beats(res, res2)[0] and not sb.beats(res2, res)[0] and not sb.beats(res, res)[0]
    row = sb.log(res, tmp_path / "scores.jsonl", "demo")
    assert json.loads((tmp_path / "scores.jsonl").read_text())["flow_f1"] == row["flow_f1"] == 1.0


def test_pid2graph(tmp_path):
    g = nx.Graph()
    for n, (label, box) in {"a": ("tank", (0, 0, 10, 10)), "c1": ("connector", (20, 4, 21, 5)),
                            "c2": ("connector", (30, 4, 31, 5)), "b": ("valve", (40, 0, 50, 10)),
                            "d": ("pump", (40, 40, 50, 50))}.items():
        g.add_node(n, label=label, xmin=box[0], ymin=box[1], xmax=box[2], ymax=box[3])
    g.add_edges_from([("a", "c1"), ("c1", "c2"), ("c2", "b"), ("c1", "d")])
    nx.write_graphml(g, tmp_path / "x.graphml")
    gold = pid2graph.symbol_connectivity(pid2graph.load(tmp_path / "x.graphml"))
    assert {frozenset(e) for e in gold.edges} == {frozenset("ab"), frozenset("ad"), frozenset("bd")}
    pred = nx.Graph()
    pred.add_node(1, bbox=(1, 0, 10, 10)); pred.add_node(2, bbox=(40, 1, 50, 10)); pred.add_node(3, bbox=(80, 80, 90, 90))
    pred.add_edges_from([(1, 2), (2, 3)])
    s = pid2graph.score_layout(pred, gold)
    assert s["nodes"] == {"precision": 0.667, "recall": 0.667, "f1": 0.667}
    assert s["edges"]["precision"] == 0.5 and s["edges"]["recall"] == 0.333


def test_cli(capsys):
    g = str(FIX / "demo_graph.json")
    for args in (["stats", g], ["describe", g], ["research", g], ["brief", g, "TK-101"],
                 ["whatif", g, "fail", "TK-101"], ["whatif", g, "isolate", "P-101"], ["whatif", g, "spof"]):
        assert main(args) == 0
    assert capsys.readouterr().out
    assert main(["brief", g, "NOPE-1"]) == 2
