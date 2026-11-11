"""Synthesis: turn the graph into text an engineer or an LLM can read.

describe(pg)    the whole plant, source to sink
brief(pg, tag)  everything known about one item, pulled from all four modules
"""

from __future__ import annotations

import networkx as nx

from ..graph import PlantGraph
from .common import attrs, instruments_near, is_equipment, kind, reach_until_equipment, sheet
from . import manipulation, research


def _order(feeds: nx.DiGraph) -> list[str]:
    """Source-to-sink order that survives recycles."""
    cond = nx.condensation(feeds)
    return [n for c in nx.topological_sort(cond) for n in sorted(cond.nodes[c]["members"])]


def _name(pg: PlantGraph, n: str) -> str:
    k = kind(pg, n).replace("_", " ")
    return f"{pg.label(n)} ({k})" if k else pg.label(n)


def _inst_phrase(pg: PlantGraph, i: str) -> str:
    a = attrs(pg, i)
    return f"{pg.label(i)} ({' '.join(x.replace('_', ' ') for x in (a.get('variable'), a.get('role')) if x) or 'instrument'})"


def describe(pg: PlantGraph) -> str:
    flow, feeds = pg.flow(), pg.feeds()
    plant = (pg.data.get("plant") or {}).get("name") or "Plant"
    out = [f"# {plant}: process description", ""]
    out.append("## Flow, source to sink")
    for n in _order(feeds):
        nxt = sorted(feeds.successors(n))
        if nxt:
            out.append(f"- {_name(pg, n)} feeds {', '.join(_name(pg, m) for m in nxt)}.")
    cycles = [c for c in nx.strongly_connected_components(feeds) if len(c) > 1]
    if cycles:
        out.append("- Recycles: " + "; ".join(" ↔ ".join(sorted(pg.label(n) for n in c)) for c in cycles) + ".")
    out += ["", "## Measurement"]
    for e in _order(feeds):
        ins = instruments_near(pg, flow, e) if pg.node(e).get("type") == "Equipment" else []
        if ins:
            out.append(f"- {pg.label(e)}: {', '.join(_inst_phrase(pg, i) for i in ins)}.")
    loops = pg.of_type("ControlLoop")
    if loops:
        out += ["", "## Control"]
        for l in sorted(loops):
            a = attrs(pg, l)
            text = a.get("description") or (
                f"{', '.join(a.get('controllers') or ['?'])} acts on {', '.join(a.get('final_elements') or ['nothing drawn'])}")
            out.append(f"- Loop {pg.label(l)} ({a.get('loop_type') or 'loop'}, {a.get('variable') or 'variable unknown'}): {text}.")
    qs = research.questions(pg)
    if qs:
        out += ["", "## Open questions", f"{len(qs)} items need an engineer's eye; the top ones:"]
        out += [f"- {q['subject']}: {q['question']}" for q in qs[:5]]
    return "\n".join(out) + "\n"


def brief(pg: PlantGraph, tag: str) -> str:
    nid = pg.find(tag)
    flow, feeds = pg.flow(), pg.feeds()
    d = pg.node(nid)
    out = [f"# {_name(pg, nid)}", "",
           f"- **Sheet:** {sheet(pg, nid) or 'unknown'}; read with confidence {d.get('confidence')}"]
    if nid in feeds:
        out.append(f"- **Fed by:** {', '.join(pg.label(n) for n in sorted(feeds.predecessors(nid))) or 'nothing drawn'}")
        out.append(f"- **Feeds:** {', '.join(pg.label(n) for n in sorted(feeds.successors(nid))) or 'nothing drawn'}")
    elif nid in flow:
        up = [n for n in reach_until_equipment(pg, flow, nid, "up") if is_equipment(pg, n)]
        dn = [n for n in reach_until_equipment(pg, flow, nid, "down") if is_equipment(pg, n)]
        out.append(f"- **Sits between:** {', '.join(pg.label(n) for n in sorted(up)) or '?'} and "
                   f"{', '.join(pg.label(n) for n in sorted(dn)) or '?'}")
    if d.get("type") == "Equipment":
        ins = instruments_near(pg, flow, nid)
        out.append(f"- **Instruments:** {', '.join(_inst_phrase(pg, i) for i in ins) or 'none found'}")
    for i in pg.out(nid, "MEASURES"):
        out.append(f"- **Measures:** {pg.label(i)}")
    for l in pg.loops_of(nid):
        out.append(f"- **Loop {pg.label(l)}:** {attrs(pg, l).get('description') or attrs(pg, l).get('loop_type')}")
    if nid in flow:
        f = manipulation.fail(pg, nid)
        lost = f["loses_supply"]["equipment"] + f["loses_supply"]["sinks"]
        out.append(f"- **If it stops:** {', '.join(lost) + (' loses supply' if len(lost) == 1 else ' lose supply') if lost else 'nothing downstream loses supply'}"
                   + (f"; {', '.join(f['instruments_blind'])} go blind" if f["instruments_blind"] else ""))
        iso = manipulation.isolate(pg, nid)
        out.append(f"- **To isolate:** close {', '.join(v['tag'] for v in iso['close']) or 'no valves found'}"
                   + ("" if iso["isolable"] else f"; no valve before {', '.join(iso['no_valve_before'])}"))
    mine = [q for q in research.questions(pg) if pg.label(nid) in q["subject"]]
    if mine:
        out.append("- **Open questions:** " + " ".join(q["question"] for q in mine))
    return "\n".join(out) + "\n"
