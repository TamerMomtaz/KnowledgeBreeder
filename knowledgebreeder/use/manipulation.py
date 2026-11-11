"""Manipulation: change a copy of the graph and report what follows.

Three what-ifs:

fail(tag)      the item stops passing flow: what loses its supply, which
               instruments go blind, which loops lose a member
isolate(tag)   which valves to close to box the item in, and where no valve
               stands between it and the next equipment
single_points  rank equipment by how much of the plant its failure starves

These are connectivity answers only. They know nothing of pressures, hold-up,
bypasses not on the drawing or procedures, so they are a starting list for an
engineer and never an isolation certificate.
"""

from __future__ import annotations

import networkx as nx

from ..graph import PlantGraph
from .common import ISOLATION_KINDS, attrs, is_equipment, kind, sheet


def _sources(pg: PlantGraph, flow: nx.DiGraph) -> set[str]:
    src = {n for n in flow if pg.node(n).get("type") == "Boundary" and attrs(pg, n).get("direction") == "source"}
    return src or {n for n in flow if flow.in_degree(n) == 0 and flow.out_degree(n) > 0}


def _supplied(flow: nx.DiGraph, sources: set[str]) -> set[str]:
    seen = set(s for s in sources if s in flow)
    for s in list(seen):
        seen |= nx.descendants(flow, s)
    return seen


def fail(pg: PlantGraph, tag: str) -> dict:
    nid = pg.find(tag)
    flow = pg.flow()
    sources = _sources(pg, flow)
    before = _supplied(flow, sources)
    cut = flow.copy()
    if nid in cut:
        cut.remove_node(nid)
    lost = before - _supplied(cut, sources - {nid}) - {nid}
    affected = lost | {nid}
    blind = sorted({i for n in affected for i in pg.measured_by(n)} |
                   {n for n in affected if pg.node(n).get("type") == "Instrument"})
    loops = sorted({l for n in list(affected) + blind for l in pg.loops_of(n)})
    return {
        "failed": pg.label(nid), "sheet": sheet(pg, nid),
        "loses_supply": {"equipment": sorted(pg.label(n) for n in lost if pg.node(n).get("type") == "Equipment"),
                         "sinks": sorted(pg.label(n) for n in lost if pg.node(n).get("type") == "Boundary"),
                         "other_items": len([n for n in lost if not is_equipment(pg, n)])},
        "still_supplied_by_another_path": sorted(pg.label(n) for n in pg.downstream(nid) - lost if is_equipment(pg, n)),
        "instruments_blind": [pg.label(i) for i in blind],
        "loops_affected": [pg.label(l) for l in loops],
    }


def isolate(pg: PlantGraph, tag: str) -> dict:
    nid = pg.find(tag)
    und = pg.flow().to_undirected()
    if nid not in und:
        raise KeyError(f"'{tag}' is not on any process line in this graph")
    valves, open_ends, inside, todo = set(), set(), {nid}, [nid]
    while todo:
        for n in und.neighbors(todo.pop()):
            if n in inside or n in valves:
                continue
            if pg.node(n).get("type") == "Component" and kind(pg, n) in ISOLATION_KINDS:
                valves.add(n)
            elif is_equipment(pg, n):
                open_ends.add(n)
            else:
                inside.add(n)
                todo.append(n)
    return {
        "item": pg.label(nid), "sheet": sheet(pg, nid),
        "close": [{"tag": pg.label(v), "kind": kind(pg, v), "sheet": sheet(pg, v)} for v in sorted(valves)],
        "no_valve_before": sorted(pg.label(n) for n in open_ends),
        "isolable": not open_ends,
        "also_inside_the_envelope": sorted(pg.label(n) for n in inside - {nid}
                                           if pg.node(n).get("type") in ("Component", "Instrument")),
    }


def single_points(pg: PlantGraph, top: int = 10) -> list[dict]:
    rows = []
    for e in pg.of_type("Equipment"):
        r = fail(pg, e)
        n = len(r["loses_supply"]["equipment"]) + len(r["loses_supply"]["sinks"])
        if n:
            rows.append({"tag": r["failed"], "starves": n, "equipment": r["loses_supply"]["equipment"],
                         "sinks": r["loses_supply"]["sinks"]})
    return sorted(rows, key=lambda r: (-r["starves"], r["tag"]))[:top]
