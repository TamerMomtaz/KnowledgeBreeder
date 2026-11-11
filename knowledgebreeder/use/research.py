"""Research: turn gaps and patterns in the graph into questions worth checking.

Each rule is a piece of process-design common sense. When the graph breaks a
rule there are three possible causes: the reader missed something, the drawing
leaves it out, or the plant really is that way. The rule cannot tell which, so
every finding is worded as a question and says where to look.

Adding a rule: write a function that yields Finding and list it in RULES.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable

import networkx as nx

from ..graph import PlantGraph
from .common import (LEVEL_KINDS, PUMP_KINDS, RELIEF_KINDS, attrs, instruments_near, kind, neighbourhood,
                     reach_until_equipment, sheet, variable)
from .manipulation import isolate


@dataclass
class Finding:
    rule: str
    priority: str      # high | medium | low
    subject: str
    question: str
    check: str
    sheet: str | None = None


def _pump_pressure(pg, flow):
    for e in pg.of_type("Equipment"):
        if kind(pg, e) in PUMP_KINDS and "pressure" not in {variable(pg, i) for i in instruments_near(pg, flow, e, "down")}:
            yield Finding("pump_discharge_pressure", "medium", pg.label(e),
                          f"{pg.label(e)} has no pressure instrument on its discharge. Is there a gauge the reader missed?",
                          "Look at the discharge line between the pump and the first valve.", sheet(pg, e))


def _level(pg, flow):
    for e in pg.of_type("Equipment"):
        if kind(pg, e) in LEVEL_KINDS and "level" not in {variable(pg, i) for i in instruments_near(pg, flow, e)}:
            yield Finding("vessel_level", "medium", pg.label(e),
                          f"{pg.label(e)} ({kind(pg, e)}) has no level instrument. How is its level known?",
                          "Look for a level gauge, transmitter or switch on the vessel outline.", sheet(pg, e))


def _relief(pg, flow):
    for e in pg.of_type("Equipment"):
        if kind(pg, e) not in RELIEF_KINDS:
            continue
        zone = neighbourhood(pg, flow, e)
        if not any(kind(pg, n) in ("relief_valve", "rupture_disc") for n in zone):
            yield Finding("pressure_relief", "high", pg.label(e),
                          f"{pg.label(e)} ({kind(pg, e)}) shows no relief valve or rupture disc. Where is it protected?",
                          "Look for a PSV or rupture disc on the item or on its connected lines.", sheet(pg, e))


def _control_valves(pg, flow):
    for c in pg.of_type("Component"):
        if kind(pg, c) == "control_valve" and not pg.loops_of(c):
            yield Finding("orphan_control_valve", "high", pg.label(c),
                          f"Control valve {pg.label(c)} belongs to no loop. What drives it?",
                          "Trace the signal line from its actuator to a controller.", sheet(pg, c))
    for l in pg.of_type("ControlLoop"):
        a = attrs(pg, l)
        if a.get("loop_type") == "control" and a.get("controllers") and not a.get("final_elements"):
            yield Finding("loop_without_final_element", "high", pg.label(l),
                          f"Loop {pg.label(l)} has a controller but no final element. What does it move?",
                          "Follow the controller output; it may cross to another sheet.", sheet(pg, l))


def _dead_ends(pg, flow):
    feeds = pg.feeds()
    for e in pg.of_type("Equipment"):
        if e not in feeds:
            continue
        if feeds.in_degree(e) and not feeds.out_degree(e) and kind(pg, e) in PUMP_KINDS | {"heat_exchanger", "filter"}:
            yield Finding("dead_end", "high", pg.label(e), f"{pg.label(e)} receives flow but sends it nowhere. Where does it go?",
                          "Check for a missed line or an unpaired off-page connector.", sheet(pg, e))
        if feeds.out_degree(e) and not feeds.in_degree(e) and kind(pg, e) in PUMP_KINDS:
            yield Finding("no_suction", "high", pg.label(e), f"{pg.label(e)} has a discharge but no suction. What feeds it?",
                          "Check the suction side for a missed line.", sheet(pg, e))


def _pump_isolation(pg, flow):
    for e in pg.of_type("Equipment"):
        if kind(pg, e) in PUMP_KINDS and e in flow:
            r = isolate(pg, e)
            if not r["isolable"]:
                yield Finding("pump_isolation", "medium", pg.label(e),
                              f"No valve between {pg.label(e)} and {', '.join(r['no_valve_before'])}. Can it be taken out for maintenance?",
                              "Look for suction and discharge isolation valves.", sheet(pg, e))


def _parallel(pg, flow):
    feeds = pg.feeds()
    groups: dict[tuple, list[str]] = {}
    for e in pg.of_type("Equipment"):
        if e in feeds and feeds.in_degree(e) and feeds.out_degree(e):
            groups.setdefault((kind(pg, e), frozenset(feeds.predecessors(e)), frozenset(feeds.successors(e))), []).append(e)
    for (k, _p, _s), members in groups.items():
        if len(members) > 1:
            tags = sorted(pg.label(m) for m in members)
            yield Finding("parallel_set", "low", " / ".join(tags),
                          f"{', '.join(tags)} are parallel {(k or 'item').replace('_', ' ')}s. Duty and standby, or do they share the load?",
                          "Check the control narrative or the equipment list.", sheet(pg, members[0]))


def _verify(pg, flow):
    for n, d in pg.g.nodes(data=True):
        if (d.get("confidence") or 1) < 0.7 and d.get("type") in ("Equipment", "Component", "Instrument"):
            yield Finding("low_confidence", "medium", pg.label(n),
                          f"{pg.label(n)} was read with confidence {d['confidence']}. Is it what the graph says it is?",
                          "Re-read this item on the drawing.", sheet(pg, n))
    inferred = [(u, v) for u, v, d in pg.edges("FLOWS_TO") if (d.get("attributes") or {}).get("flow_direction") == "inferred"]
    eq = {pg.label(n) for u, v in inferred for n in (u, v) if pg.node(n).get("type") == "Equipment"}
    if inferred:
        yield Finding("inferred_direction", "medium", ", ".join(sorted(eq)) or f"{len(inferred)} edges",
                      f"Flow direction was inferred, not drawn, on {len(inferred)} edges. Is the direction right?",
                      "Look for flow arrows near these items.", None)


RULES: list[Callable[[PlantGraph, nx.DiGraph], Iterable[Finding]]] = [
    _relief, _control_valves, _dead_ends, _pump_pressure, _level, _pump_isolation, _verify, _parallel]


def questions(pg: PlantGraph) -> list[dict]:
    flow = pg.flow()
    found = [f for rule in RULES for f in rule(pg, flow)]
    rank = {"high": 0, "medium": 1, "low": 2}
    return [asdict(f) for f in sorted(found, key=lambda f: (rank[f.priority], f.rule, f.subject))]


def to_markdown(qs: list[dict]) -> str:
    out = ["# Questions worth checking", "",
           "Each one may be a reading miss, a drawing omission or a real feature of the plant. An engineer decides.", ""]
    for p in ("high", "medium", "low"):
        rows = [q for q in qs if q["priority"] == p]
        if rows:
            out.append(f"## {p.capitalize()} priority")
            out += [f"- **{q['subject']}**" + (f" (sheet {q['sheet']})" if q["sheet"] else "") + f": {q['question']} *{q['check']}*"
                    for q in rows]
            out.append("")
    return "\n".join(out)
