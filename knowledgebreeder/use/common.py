"""Helpers shared by the use modules."""

from __future__ import annotations

import networkx as nx

from ..graph import EQUIPMENT_LIKE, PlantGraph

ISOLATION_KINDS = {"manual_valve", "gate_valve", "globe_valve", "ball_valve", "butterfly_valve", "plug_valve",
                   "knife_gate_valve", "diaphragm_valve", "pinch_valve", "on_off_valve", "motor_operated_valve",
                   "blind", "spectacle_blind"}
PUMP_KINDS = {"pump", "centrifugal_pump", "positive_displacement_pump", "metering_pump", "slurry_pump", "sump_pump"}
LEVEL_KINDS = {"tank", "vessel", "pressure_vessel", "agitated_tank", "sump", "column", "reactor", "separator",
               "clarifier", "thickener", "boiler"}
RELIEF_KINDS = {"pressure_vessel", "boiler", "reactor", "column", "compressor", "positive_displacement_pump"}


def kind(pg: PlantGraph, nid: str) -> str:
    return pg.node(nid).get("kind") or ""


def attrs(pg: PlantGraph, nid: str) -> dict:
    return pg.node(nid).get("attributes") or {}


def is_equipment(pg: PlantGraph, nid: str) -> bool:
    return pg.node(nid).get("type") in EQUIPMENT_LIKE


def sheet(pg: PlantGraph, nid: str) -> str | None:
    s = pg.node(nid).get("sheets") or []
    return s[0].replace("SHEET:", "") if s else None


def reach_until_equipment(pg: PlantGraph, flow: nx.DiGraph, start: str, direction: str) -> set[str]:
    """Everything between ``start`` and the next equipment in one direction, that equipment included."""
    step = flow.successors if direction == "down" else flow.predecessors
    seen, todo = set(), [start]
    while todo:
        for n in step(todo.pop()):
            if n in seen:
                continue
            seen.add(n)
            if not is_equipment(pg, n):
                todo.append(n)
    return seen


def neighbourhood(pg: PlantGraph, flow: nx.DiGraph, eq: str) -> set[str]:
    """The equipment plus its piping up to the neighbouring equipment on both sides."""
    return {eq} | reach_until_equipment(pg, flow, eq, "up") | reach_until_equipment(pg, flow, eq, "down")


def instruments_near(pg: PlantGraph, flow: nx.DiGraph, eq: str, side: str = "both") -> list[str]:
    zone = {eq}
    if side in ("both", "up"):
        zone |= reach_until_equipment(pg, flow, eq, "up")
    if side in ("both", "down"):
        zone |= reach_until_equipment(pg, flow, eq, "down")
    zone = {n for n in zone if n == eq or not is_equipment(pg, n)}
    found = {i for n in zone for i in pg.measured_by(n)}
    found |= {n for n in zone if pg.node(n).get("type") == "Instrument"}
    return sorted(found)


def variable(pg: PlantGraph, inst: str) -> str:
    return attrs(pg, inst).get("variable") or ""
