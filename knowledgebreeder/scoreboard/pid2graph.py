"""Load PID2Graph ground truth (DLR, Zenodo 14803338, CC BY-SA 4.0).

Each drawing there comes with a .graphml file: symbols are nodes with a
bounding box (xmin, ymin, xmax, ymax) and a label; lines are edges; nodes
labelled "connector" are line corners and junctions, not symbols.

``symbol_connectivity`` collapses the connectors, leaving which symbol is
connected to which. ``score_layout`` then scores any predicted layout graph
(nodes with boxes, edges between them) by matching boxes first.

STATUS: written from the dataset's published description and tested on a
graphml file made to that description. It has not yet been run against the
real 9.3 GB download; attribute names may need adjusting when it is.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

NON_SYMBOLS = {"connector", "crossing", "border_node", "border-node", "background"}


def load(path: str | Path) -> nx.Graph:
    g = nx.Graph(nx.read_graphml(path))
    for _n, d in g.nodes(data=True):
        d["bbox"] = tuple(float(d.get(k, 0)) for k in ("xmin", "ymin", "xmax", "ymax"))
        d["label"] = str(d.get("label", "")).lower()
    return g


def symbol_connectivity(g: nx.Graph) -> nx.Graph:
    """Symbols only, joined when a path of connectors links them."""
    symbols = {n for n, d in g.nodes(data=True) if d["label"] not in NON_SYMBOLS}
    out = nx.Graph()
    out.add_nodes_from((n, g.nodes[n]) for n in symbols)
    for s in symbols:
        seen, todo = {s}, [s]
        while todo:
            for n in g.neighbors(todo.pop()):
                if n in seen:
                    continue
                seen.add(n)
                if n in symbols:
                    out.add_edge(s, n)
                else:
                    todo.append(n)
    return out


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def score_layout(pred: nx.Graph, gold: nx.Graph, iou_min: float = 0.5) -> dict:
    """Match predicted boxes to gold boxes greedily by IoU, then compare edges."""
    pairs = sorted(((_iou(pd["bbox"], gd["bbox"]), p, q) for p, pd in pred.nodes(data=True)
                    for q, gd in gold.nodes(data=True)), key=lambda t: -t[0])
    match: dict = {}
    used = set()
    for iou, p, q in pairs:
        if iou < iou_min:
            break
        if p not in match and q not in used:
            match[p] = q
            used.add(q)

    def f1(tp, n_pred, n_gold):
        p = tp / n_pred if n_pred else 0.0
        r = tp / n_gold if n_gold else 0.0
        return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}

    gold_edges = {frozenset(e) for e in gold.edges}
    pred_edges = {frozenset((match[u], match[v])) for u, v in pred.edges if u in match and v in match}
    return {"nodes": f1(len(match), pred.number_of_nodes(), gold.number_of_nodes()),
            "edges": f1(len(pred_edges & gold_edges), pred.number_of_edges(), gold.number_of_edges())}
