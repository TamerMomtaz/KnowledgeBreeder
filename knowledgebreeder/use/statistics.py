"""Statistics: measure the plant, and measure how far the graph can be trusted."""

from __future__ import annotations

from collections import Counter
from statistics import mean

import networkx as nx

from ..graph import PlantGraph
from .common import attrs, instruments_near, is_equipment, kind


def stats(pg: PlantGraph) -> dict:
    g, flow, feeds = pg.g, pg.flow(), pg.feeds()
    types = pg.type_counts()
    equipment = pg.of_type("Equipment")
    instruments = pg.of_type("Instrument")
    loops = pg.of_type("ControlLoop")

    conf = [d.get("confidence") for _n, d in g.nodes(data=True) if d.get("confidence") is not None]
    flows = list(pg.edges("FLOWS_TO"))
    inferred = [e for e in flows if (e[2].get("attributes") or {}).get("flow_direction") == "inferred"]

    bare = [pg.label(e) for e in equipment if not instruments_near(pg, flow, e)]
    cvs = [n for n in pg.of_type("Component") if kind(pg, n) == "control_valve"]
    cv_no_loop = [pg.label(n) for n in cvs if not pg.loops_of(n)]

    order = None
    if feeds.number_of_nodes() and nx.is_directed_acyclic_graph(feeds):
        order = [pg.label(n) for n in nx.dag_longest_path(feeds)]
    between = nx.betweenness_centrality(feeds) if feeds.number_of_edges() else {}
    hubs = sorted(((round(v, 3), pg.label(n)) for n, v in between.items() if v > 0 and is_equipment(pg, n)), reverse=True)

    return {
        "size": {"nodes": g.number_of_nodes(), "edges": g.number_of_edges(), "by_type": dict(types),
                 "edges_by_type": dict(Counter(d.get("type") for *_x, d in g.edges(data=True)))},
        "equipment_by_kind": dict(Counter(kind(pg, n) or "unknown" for n in equipment).most_common()),
        "instruments_by_variable": dict(Counter(attrs(pg, n).get("variable") or "unknown" for n in instruments).most_common()),
        "loops_by_type": dict(Counter(attrs(pg, n).get("loop_type") or kind(pg, n) or "unknown" for n in loops)),
        "density": {"instruments_per_equipment": round(len(instruments) / len(equipment), 2) if equipment else None,
                    "loops_per_equipment": round(len(loops) / len(equipment), 2) if equipment else None},
        "topology": {"sources": sorted(pg.label(n) for n in feeds if feeds.in_degree(n) == 0 and feeds.out_degree(n) > 0),
                     "sinks": sorted(pg.label(n) for n in feeds if feeds.out_degree(n) == 0 and feeds.in_degree(n) > 0),
                     "recycles": sum(1 for _ in nx.simple_cycles(feeds)) if feeds.number_of_nodes() < 400 else None,
                     "longest_path": order, "busiest_equipment": [{"tag": t, "betweenness": v} for v, t in hubs[:5]]},
        "coverage": {"equipment_without_instruments": sorted(bare),
                     "control_valves_outside_loops": sorted(cv_no_loop)},
        "trust": {"mean_confidence": round(mean(conf), 3) if conf else None,
                  "nodes_below_0.7": sorted(pg.label(n) for n, d in g.nodes(data=True) if (d.get("confidence") or 1) < 0.7),
                  "inferred_flow_share": round(len(inferred) / len(flows), 3) if flows else None,
                  "open_issues": len(pg.data.get("issues") or [])},
    }


def to_markdown(s: dict) -> str:
    out = ["# Plant statistics", ""]
    out.append(f"- **Size:** {s['size']['nodes']} nodes, {s['size']['edges']} edges")
    for title, key in (("Equipment", "equipment_by_kind"), ("Instruments", "instruments_by_variable"), ("Loops", "loops_by_type")):
        if s[key]:
            out.append(f"- **{title}:** " + ", ".join(f"{k} {v}" for k, v in s[key].items()))
    t = s["topology"]
    out.append(f"- **Sources:** {', '.join(t['sources']) or 'none'}")
    out.append(f"- **Sinks:** {', '.join(t['sinks']) or 'none'}")
    if t["longest_path"]:
        out.append(f"- **Longest path:** {' → '.join(t['longest_path'])}")
    if t["busiest_equipment"]:
        out.append("- **Busiest equipment:** " + ", ".join(b["tag"] for b in t["busiest_equipment"]))
    c, tr = s["coverage"], s["trust"]
    out.append(f"- **Equipment with no instrument nearby:** {', '.join(c['equipment_without_instruments']) or 'none'}")
    out.append(f"- **Control valves outside any loop:** {', '.join(c['control_valves_outside_loops']) or 'none'}")
    out.append(f"- **Trust:** mean confidence {tr['mean_confidence']}, inferred flow direction on "
               f"{tr['inferred_flow_share']:.0%} of flow edges, {len(tr['nodes_below_0.7'])} low-confidence items"
               if tr["inferred_flow_share"] is not None else f"- **Trust:** mean confidence {tr['mean_confidence']}")
    return "\n".join(out) + "\n"
