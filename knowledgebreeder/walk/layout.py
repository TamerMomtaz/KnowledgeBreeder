"""Where each item of a plant goes on the page.

The graph says what is joined to what. It does not say where anything stands,
so the places here are made up by kb: columns follow the flow from source to
sink, and each branch gets a row of its own under the line it leaves.

    column   how far along the flow an item is (the longest way to reach it)
    row      0 is the longest line through the plant; branches stack below it
    hop      one stretch of pipe from a column to the next

A pipe segment with one way in and one way out is not drawn as an item. It
becomes part of the line between its neighbours. A segment where lines meet or
part is drawn as a junction. A line that runs back upstream (a recycle) is kept
apart so the page can draw it under the plant.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..graph import PlantGraph
from ..use.common import attrs


@dataclass
class Line:
    """A run of pipe between two drawn items."""
    u: str
    v: str
    through: list[str] = field(default_factory=list)    # the pipe segments it is made of
    inferred: bool = False                              # the flow direction was guessed, not drawn
    back: bool = False                                  # runs upstream
    way: list[str] = field(default_factory=list)        # bends kept free for it, one per column it crosses


@dataclass
class Sketch:
    col: dict[str, int]
    row: dict[str, int]
    lines: list[Line]
    loose: list[str]                                    # items on no line at all
    carrier: dict[str, int]                             # pipe segment -> the line that holds it

    @property
    def items(self) -> list[str]:
        """Drawn items in walking order: along the flow, top row first."""
        return sorted((n for n in self.col if not n.startswith("~")), key=lambda n: (self.col[n], self.row[n], n))


def _is_segment(pg: PlantGraph, n: str) -> bool:
    return pg.node(n).get("type") == "PipeSegment"


def _lines(pg: PlantGraph, flow: nx.DiGraph) -> tuple[list[Line], set[str]]:
    through = {n for n in flow if _is_segment(pg, n) and flow.in_degree(n) == 1 and flow.out_degree(n) == 1}
    guessed = {(u, v) for u, v, d in pg.edges("FLOWS_TO")
               if (d.get("attributes") or {}).get("flow_direction") == "inferred"}
    found: dict[tuple[str, str], Line] = {}
    for u in flow:
        if u in through:
            continue
        for s in flow.successors(u):
            chain, prev, inferred = [], u, False
            while s in through and s not in chain:
                inferred |= (prev, s) in guessed
                chain.append(s)
                prev, s = s, next(iter(flow.successors(s)))
            if s in through:                            # a ring of bare pipe with no item on it
                continue
            inferred |= (prev, s) in guessed
            line = found.setdefault((u, s), Line(u, s))
            line.through += chain
            line.inferred |= inferred
    return list(found.values()), through


def _back_edges(h: nx.DiGraph, roots: list[str]) -> set[tuple[str, str]]:
    """Edges that close a ring, found by walking from the sources."""
    seen: dict[str, int] = {}
    back = set()
    for r in roots:
        if r in seen:
            continue
        seen[r] = 1
        stack = [(r, iter(sorted(h.successors(r))))]
        while stack:
            n, it = stack[-1]
            for m in it:
                if seen.get(m) == 1:
                    back.add((n, m))
                elif m not in seen:
                    seen[m] = 1
                    stack.append((m, iter(sorted(h.successors(m)))))
                    break
            else:
                seen[n] = 2
                stack.pop()
    return back


def sketch(pg: PlantGraph, flow: nx.DiGraph | None = None) -> Sketch:
    flow = flow if flow is not None else pg.flow()
    lines, through = _lines(pg, flow)
    on_line = {n for ln in lines for n in (ln.u, ln.v)}
    loose = sorted(n for n in flow if n not in on_line and n not in through and not _is_segment(pg, n))

    h = nx.DiGraph()
    h.add_nodes_from(sorted(on_line))
    h.add_edges_from((ln.u, ln.v) for ln in lines if ln.u != ln.v)

    def is_source(n):
        return pg.node(n).get("type") == "Boundary" and attrs(pg, n).get("direction") == "source"
    roots = sorted(h, key=lambda n: (not is_source(n), h.in_degree(n) > 0, n))
    back = _back_edges(h, roots)
    for ln in lines:
        ln.back = ln.u == ln.v or (ln.u, ln.v) in back
    dag = nx.DiGraph()
    dag.add_nodes_from(h)
    dag.add_edges_from(e for e in h.edges if e not in back)

    order = list(nx.lexicographical_topological_sort(dag))
    col = {n: 0 for n in dag}
    for n in order:
        for s in dag.successors(n):
            col[s] = max(col[s], col[n] + 1)
    for n in reversed(order):                           # stand next to what you feed, when nothing is lost by it
        if dag.out_degree(n) and dag.out_degree(n) >= dag.in_degree(n):
            col[n] = max(col[n], min(col[s] for s in dag.successors(n)) - 1)

    g = nx.DiGraph()                                    # the same graph with a bend in every column a line crosses
    g.add_nodes_from(dag)
    for k, ln in enumerate(lines):
        if ln.back:
            continue
        ln.way = [f"~{k}.{c}" for c in range(col[ln.u] + 1, col[ln.v])]
        for c, d in zip(range(col[ln.u] + 1, col[ln.v]), ln.way):
            col[d] = c
        nx.add_path(g, [ln.u, *ln.way, ln.v])

    order = list(nx.lexicographical_topological_sort(g))
    ahead = {n: 0 for n in g}                           # the longest way on to a sink
    behind = {n: 0 for n in g}                          # the longest way back to a source
    for n in reversed(order):
        ahead[n] = max((ahead[s] + 1 for s in g.successors(n)), default=0)
    for n in order:
        behind[n] = max((behind[p] + 1 for p in g.predecessors(n)), default=0)

    def bend(n):
        return n.startswith("~")

    def main_next(n):
        return min(g.successors(n), key=lambda s: (-ahead[s], bend(s), s), default=None)

    runs: list[list[str]] = []                          # each run is one straight line of items
    run_of: dict[str, int] = {}
    came_from: dict[str, str | None] = {}

    def best(n, preds):
        """The line a meeting point belongs to: the longest way back, and among equals the older line."""
        return min(preds, key=lambda p: (-behind[p], bend(p), run_of[p], p), default=None)

    for n in order:
        straight = best(n, [p for p in g.predecessors(n) if main_next(p) == n])
        came_from[n] = straight if straight is not None else best(n, list(g.predecessors(n)))
        if straight is not None and runs[run_of[straight]][-1] == straight:
            run_of[n] = run_of[straight]
            runs[run_of[n]].append(n)
        else:
            run_of[n] = len(runs)
            runs.append([n])

    def parent(i):
        first, last = runs[i][0], runs[i][-1]
        if came_from[first] is not None:
            return run_of[came_from[first]]
        s = main_next(last)
        return run_of[s] if s is not None else None

    def weight(i):
        """Longest first. Among branches, one that leaves a line and joins it again stays next to it."""
        loop = came_from[runs[i][0]] is not None and main_next(runs[i][-1]) is not None
        return (not loop, -sum(1 for n in runs[i] if not bend(n)), -len(runs[i]), col[runs[i][0]], runs[i][0])

    row: dict[str, int] = {}
    taken: set[tuple[int, int]] = set()
    run_row: dict[int, int] = {}

    def place(i, r):
        cells = [(col[n], r) for n in runs[i]]
        while any(c in taken for c in cells):
            r += 1
            cells = [(col[n], r) for n in runs[i]]
        taken.update(cells)
        run_row[i] = r
        for n in runs[i]:
            row[n] = r

    beside = {i: set() for i in range(len(runs))}       # runs joined by any line
    for a, b in g.edges:
        if run_of[a] != run_of[b]:
            beside[run_of[a]].add(run_of[b])
            beside[run_of[b]].add(run_of[a])

    def home(i):
        """The row to start looking from: the line it leaves or joins, else any placed line it touches."""
        p = parent(i)
        if p in run_row:
            return run_row[p]
        rows = [run_row[j] for j in beside[i] if j in run_row]
        return min(rows) if rows else None

    waiting = sorted(range(len(runs)), key=weight)
    if waiting:
        first = min(waiting, key=lambda i: weight(i)[1:])   # the longest line of all is row 0
        waiting.remove(first)
        place(first, 0)
    while waiting:
        i = next((i for i in waiting if home(i) is not None), None)
        if i is not None:
            place(i, home(i))                           # that row when it is free there, else the next free one below
        else:                                           # a part of the plant joined to nothing placed so far
            i = waiting[0]
            place(i, max(run_row.values(), default=-1) + 1)
        waiting.remove(i)

    carrier = {s: k for k, ln in enumerate(lines) for s in ln.through}
    return Sketch(col, row, lines, loose, carrier)
