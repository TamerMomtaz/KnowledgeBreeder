"""Load a plant graph (the seed's graph.json) and answer the basic walks every use module needs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import networkx as nx

PROCESS_EDGES = {"FLOWS_TO"}
EQUIPMENT_LIKE = {"Equipment", "Boundary"}


class PlantGraph:
    def __init__(self, data: dict):
        self.data = data
        self.g = nx.MultiDiGraph()
        for n in data.get("nodes", []):
            self.g.add_node(n["id"], **n)
        for e in data.get("edges", []):
            self.g.add_edge(e["source"], e["target"], key=e.get("id") or e["type"], **e)

    @classmethod
    def load(cls, path: str | Path) -> "PlantGraph":
        p = Path(path)
        if p.is_dir():
            p = p / "graph.json"
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # -------------------------------------------------------------- lookup
    def node(self, nid: str) -> dict:
        return self.g.nodes[nid]

    def find(self, tag_or_id: str) -> str:
        """Resolve a tag (case and dash insensitive) or a node id."""
        if tag_or_id in self.g:
            return tag_or_id
        want = _norm(tag_or_id)
        hits = [n for n, d in self.g.nodes(data=True) if _norm(d.get("tag") or "") == want
                or _norm(d.get("label") or "") == want]
        if not hits:
            raise KeyError(f"no node with tag or id '{tag_or_id}'")
        return hits[0]

    def label(self, nid: str) -> str:
        d = self.g.nodes[nid]
        return d.get("tag") or d.get("label") or nid

    def of_type(self, *types: str) -> list[str]:
        return [n for n, d in self.g.nodes(data=True) if d.get("type") in types]

    def edges(self, etype: str) -> Iterable[tuple[str, str, dict]]:
        for u, v, d in self.g.edges(data=True):
            if d.get("type") == etype:
                yield u, v, d

    def out(self, nid: str, etype: str) -> list[str]:
        return [v for _u, v, d in self.g.out_edges(nid, data=True) if d.get("type") == etype]

    def into(self, nid: str, etype: str) -> list[str]:
        return [u for u, _v, d in self.g.in_edges(nid, data=True) if d.get("type") == etype]

    # -------------------------------------------------------------- views
    def flow(self, etypes: set[str] = PROCESS_EDGES) -> nx.DiGraph:
        f = nx.DiGraph()
        f.add_nodes_from(n for n, d in self.g.nodes(data=True)
                         if d.get("type") not in {"Plant", "Sheet", "ControlLoop", "Instrument"}
                         or (d.get("attributes") or {}).get("inline"))
        for u, v, _d in self.g.edges(data=True):
            if _d.get("type") in etypes:
                f.add_edge(u, v)
        return f

    def feeds(self) -> nx.DiGraph:
        f = nx.DiGraph()
        f.add_nodes_from(self.of_type(*EQUIPMENT_LIKE))
        f.add_edges_from((u, v) for u, v, _d in self.edges("FEEDS"))
        if f.number_of_edges() == 0:  # graphs built without FEEDS: collapse FLOWS_TO ourselves
            fl = self.flow()
            eq = set(f.nodes)
            for s in eq:
                if s not in fl:
                    continue
                for t in nx.descendants(fl, s) & eq:
                    path = nx.shortest_path(fl, s, t)
                    if not (set(path[1:-1]) & eq):
                        f.add_edge(s, t)
        return f

    def upstream(self, nid: str) -> set[str]:
        fl = self.flow()
        return nx.ancestors(fl, nid) if nid in fl else set()

    def downstream(self, nid: str) -> set[str]:
        fl = self.flow()
        return nx.descendants(fl, nid) if nid in fl else set()

    def measured_by(self, nid: str) -> list[str]:
        return self.into(nid, "MEASURES")

    def loops_of(self, nid: str) -> list[str]:
        return self.out(nid, "MEMBER_OF")

    def loop_members(self, loop_id: str) -> list[tuple[str, str]]:
        return [(u, (d.get("attributes") or {}).get("role") or d.get("role") or "?")
                for u, _v, d in self.g.in_edges(loop_id, data=True) if d.get("type") == "MEMBER_OF"]

    def type_counts(self) -> Counter:
        return Counter(d.get("type") for _n, d in self.g.nodes(data=True))

    def copy(self) -> "PlantGraph":
        c = PlantGraph.__new__(PlantGraph)
        c.data = self.data
        c.g = self.g.copy()
        return c


def _norm(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())
