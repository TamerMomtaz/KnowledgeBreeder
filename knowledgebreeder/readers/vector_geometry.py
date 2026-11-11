"""Vector-geometry reader: read the pipe network straight out of a vector PDF.

On a CAD-exported P&ID, every pipe is drawn as a path whose coordinates are
exact. The seed skill counts those paths to classify the page and then throws
them away, asking the model to trace the lines on a rendered image. This reader
keeps them. It returns:

* ``segments``: straight line pieces after merging, each solid or dashed;
* ``nodes``: snapped endpoints, corners, junctions and tees;
* ``runs``: connected pipe networks, with the boxes and symbols they touch;
* ``boxes``: large closed shapes (candidate equipment outlines);
* ``symbols``: clusters of small closed or curved shapes (candidate valves,
  instrument bubbles, arrows);
* ``tags``: tag-like text from the text layer, attached to the nearest
  box, symbol or run.

It is a skeleton for the model to label, not a finished graph: a run tells
the model "these ends are connected"; the model still decides which symbol is
a valve, which way flow goes and which tag belongs to what.

Coordinates in the output are normalized to the page, origin at top left,
the same convention the seed's hints use. Known limits: curved pipes are
ignored, pages with a /Rotate entry or a mediabox offset are not corrected
beyond the ``rotation`` argument, and outlined text (no text layer) gives no
tags; join the seed's OCR hints for those.
"""

from __future__ import annotations

import ctypes
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .base import ReaderResult

TAG_RE = re.compile(r"^[A-Z]{1,5}[- ]?\d{2,5}[A-Z]?$|^\d{2,4}-[A-Z]{1,5}-?\d{2,5}[A-Z]?$")


@dataclass
class Params:
    snap_tol: float = 1.5        # pt: endpoints closer than this are one node
    min_len: float = 1.0         # pt: shorter straight pieces are dropped
    symbol_max: float = 40.0     # pt: closed/curved subpaths at most this big are symbol parts
    box_min: float = 40.0        # pt: closed subpaths at least this big (both sides) are boxes
    frame_margin: float = 0.02   # fraction of page: geometry this close to every edge is the border
    gap_tol: float = 4.0         # pt: collinear pieces closer than this are merged
    tag_radius: float = 36.0     # pt: tags further than this from anything stay unattached
    max_segments: int = 60000    # above this the page is too dense to trust; warn


@dataclass
class Seg:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    dashed: bool

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


# ---------------------------------------------------------------- PDF access

def _mat_mul(m: tuple, n: tuple) -> tuple:
    """Compose affine matrices (a,b,c,d,e,f): apply m first, then n."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _apply(m: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _obj_matrix(raw, obj) -> tuple:
    m = raw.FS_MATRIX()
    if raw.FPDFPageObj_GetMatrix(obj, ctypes.byref(m)):
        return (m.a, m.b, m.c, m.d, m.e, m.f)
    return IDENTITY


def _iter_paths(raw, handles: Iterable, parent: tuple) -> Iterable[tuple]:
    """Yield (path_obj, page_matrix) for every path, descending into form XObjects."""
    for obj in handles:
        t = raw.FPDFPageObj_GetType(obj)
        m = _mat_mul(_obj_matrix(raw, obj), parent)
        if t == raw.FPDF_PAGEOBJ_PATH:
            yield obj, m
        elif t == raw.FPDF_PAGEOBJ_FORM:
            n = raw.FPDFFormObj_CountObjects(obj)
            yield from _iter_paths(raw, (raw.FPDFFormObj_GetObject(obj, i) for i in range(n)), m)


def _subpaths(raw, obj, m: tuple) -> list[dict]:
    """Split one path object into subpaths of page-space points."""
    out: list[dict] = []
    cur: dict | None = None
    x, y = ctypes.c_float(), ctypes.c_float()
    for i in range(raw.FPDFPath_CountSegments(obj)):
        s = raw.FPDFPath_GetPathSegment(obj, i)
        raw.FPDFPathSegment_GetPoint(s, ctypes.byref(x), ctypes.byref(y))
        p = _apply(m, x.value, y.value)
        kind = raw.FPDFPathSegment_GetType(s)
        if kind == raw.FPDF_SEGMENT_MOVETO or cur is None:
            cur = {"pts": [p], "curved": False, "closed": False}
            out.append(cur)
            if kind == raw.FPDF_SEGMENT_MOVETO:
                continue
        if kind == raw.FPDF_SEGMENT_BEZIERTO:
            cur["curved"] = True
        cur["pts"].append(p)
        if raw.FPDFPathSegment_GetClose(s):
            cur["closed"] = True
            cur["pts"].append(cur["pts"][0])
    for sp in out:  # a polygon drawn back to its start without a close flag is closed too
        pts = sp["pts"]
        if len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.5:
            sp["closed"] = True
    return out


def _style(raw, obj, scale: float) -> tuple[float, bool, bool, bool]:
    """(stroke width, dashed, stroked, filled)."""
    w = ctypes.c_float(0)
    raw.FPDFPageObj_GetStrokeWidth(obj, ctypes.byref(w))
    fill, stroke = ctypes.c_int(0), ctypes.c_int(0)
    raw.FPDFPath_GetDrawMode(obj, ctypes.byref(fill), ctypes.byref(stroke))
    dashed = False
    if hasattr(raw, "FPDFPageObj_GetDashCount"):
        dashed = raw.FPDFPageObj_GetDashCount(obj) > 0
    return w.value * scale, dashed, bool(stroke.value), bool(fill.value)


def _bbox(pts: list[tuple]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- geometry

class _Grid:
    """Bucket index for nearest-point and point-on-segment queries."""

    def __init__(self, cell: float):
        self.cell = cell
        self.b: dict[tuple[int, int], list] = defaultdict(list)

    def _keys(self, x0, y0, x1, y1):
        c = self.cell
        for i in range(int(x0 // c), int(x1 // c) + 1):
            for j in range(int(y0 // c), int(y1 // c) + 1):
                yield i, j

    def add(self, item, x0, y0, x1, y1):
        for k in self._keys(x0, y0, x1, y1):
            self.b[k].append(item)

    def near(self, x, y, r):
        seen = set()
        for k in self._keys(x - r, y - r, x + r, y + r):
            for it in self.b.get(k, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    yield it


def _merge_collinear(segs: list[Seg], gap_tol: float) -> tuple[list[Seg], int]:
    """Join horizontal/vertical pieces that continue each other.

    Lines that CAD drew as many short dashes come out as one segment marked
    dashed. Returns the merged list and how many pieces were absorbed.
    """
    groups: dict[tuple, list[Seg]] = defaultdict(list)
    rest: list[Seg] = []
    for s in segs:
        if abs(s.y1 - s.y2) < 0.3:
            groups[("h", round((s.y1 + s.y2) / 2, 0), round(s.width, 1))].append(s)
        elif abs(s.x1 - s.x2) < 0.3:
            groups[("v", round((s.x1 + s.x2) / 2, 0), round(s.width, 1))].append(s)
        else:
            rest.append(s)
    out, absorbed = list(rest), 0
    for (axis, k, _w), items in groups.items():
        spans = sorted(((min(s.x1, s.x2), max(s.x1, s.x2), s) if axis == "h"
                        else (min(s.y1, s.y2), max(s.y1, s.y2), s)) for s in items)
        cur_a, cur_b, first = spans[0][0], spans[0][1], spans[0][2]
        pieces, gaps, dashed = 1, 0, first.dashed
        def flush():
            nonlocal out
            is_dashed = dashed or (pieces >= 3 and gaps >= 2)
            if axis == "h":
                out.append(Seg(cur_a, k, cur_b, k, first.width, is_dashed))
            else:
                out.append(Seg(k, cur_a, k, cur_b, first.width, is_dashed))
        for a, b, s in spans[1:]:
            if a <= cur_b + gap_tol and s.dashed == first.dashed:
                if a > cur_b + 0.3:
                    gaps += 1
                cur_b = max(cur_b, b)
                pieces += 1
                absorbed += 1
            else:
                flush()
                cur_a, cur_b, first, pieces, gaps, dashed = a, b, s, 1, 0, s.dashed
        flush()
    return out, absorbed


def _union_find(n: int):
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    return find, union


def _point_seg_dist(px, py, s: Seg) -> tuple[float, float]:
    """Distance from a point to a segment, and the projection parameter t in [0,1]."""
    dx, dy = s.x2 - s.x1, s.y2 - s.y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist((px, py), (s.x1, s.y1)), 0.0
    t = max(0.0, min(1.0, ((px - s.x1) * dx + (py - s.y1) * dy) / L2))
    return math.dist((px, py), (s.x1 + t * dx, s.y1 + t * dy)), t


def _near_rect(x, y, r, tol) -> bool:
    x0, y0, x1, y1 = r
    return x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol


def build_skeleton(subpaths: list[dict], page_w: float, page_h: float,
                   texts: list[dict], p: Params) -> dict:
    """Pure geometry: classify subpaths, merge, snap, find tees, group runs.

    ``subpaths``: dicts with pts (page points, PDF coords), curved, closed,
    width, dashed, filled, stroked. ``texts``: dicts with text and bbox in
    PDF coords (x0, y0, x1, y1).
    """
    mx, my = page_w * p.frame_margin, page_h * p.frame_margin
    symbol_parts: list[tuple] = []   # (bbox, filled)
    boxes: list[tuple] = []
    raw_segs: list[Seg] = []
    skipped_fill = 0

    def in_frame(b):
        x0, y0, x1, y1 = b
        return x0 < mx or y0 < my or x1 > page_w - mx or y1 > page_h - my

    for sp in subpaths:
        pts = sp["pts"]
        if len(pts) < 2:
            continue
        b = _bbox(pts)
        bw, bh = b[2] - b[0], b[3] - b[1]
        small = max(bw, bh) <= p.symbol_max
        if sp["filled"] and not sp["stroked"]:
            if small:
                symbol_parts.append((b, True))  # arrowheads, solid symbols
            skipped_fill += 1                   # outlined text and hatching land here too
            continue
        if small and (sp["closed"] or sp["curved"]):
            symbol_parts.append((b, sp["filled"]))
            continue
        if sp["closed"] and bw >= p.box_min and bh >= p.box_min and not sp["curved"]:
            if not (bw > page_w * 0.8 and bh > page_h * 0.8):
                boxes.append(b)
            continue  # a box, or the drawing frame: either way not a pipe
        if sp["curved"]:
            continue  # curved pipes and large round shapes: left to the model
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            s = Seg(x1, y1, x2, y2, sp["width"], sp["dashed"])
            if s.length >= p.min_len and not in_frame((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))):
                raw_segs.append(s)

    segs, absorbed = _merge_collinear(raw_segs, p.gap_tol)

    # symbols: cluster overlapping small shapes
    find, union = _union_find(len(symbol_parts))
    g = _Grid(max(p.symbol_max, 10.0))
    for i, (b, _f) in enumerate(symbol_parts):
        g.add(i, *b)
    for i, (b, _f) in enumerate(symbol_parts):
        for j in g.near((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, p.symbol_max):
            if j != i and _near_rect((symbol_parts[j][0][0] + symbol_parts[j][0][2]) / 2,
                                     (symbol_parts[j][0][1] + symbol_parts[j][0][3]) / 2,
                                     b, p.snap_tol + (symbol_parts[j][0][2] - symbol_parts[j][0][0]) / 2):
                union(i, j)
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(symbol_parts)):
        clusters[find(i)].append(i)
    symbols = []
    for members in clusters.values():
        bb = _bbox([pt for i in members for pt in ((symbol_parts[i][0][0], symbol_parts[i][0][1]),
                                                     (symbol_parts[i][0][2], symbol_parts[i][0][3]))])
        filled = all(symbol_parts[i][1] for i in members)
        size = max(bb[2] - bb[0], bb[3] - bb[1])
        symbols.append({"bbox": bb, "parts": len(members),
                        "hint": "possible_arrow" if filled and size < 8 else None})

    # nodes: snap endpoints
    seg_grid = _Grid(50.0)
    for s in segs:
        seg_grid.add(s, min(s.x1, s.x2), min(s.y1, s.y2), max(s.x1, s.x2), max(s.y1, s.y2))
    node_xy: list[tuple[float, float]] = []
    node_grid = _Grid(max(p.snap_tol * 4, 5.0))

    def node_at(x, y) -> int:
        for k in node_grid.near(x, y, p.snap_tol):
            if math.dist(node_xy[k], (x, y)) <= p.snap_tol:
                return k
        node_xy.append((x, y))
        node_grid.add(len(node_xy) - 1, x, y, x, y)
        return len(node_xy) - 1

    seg_ends = [(node_at(s.x1, s.y1), node_at(s.x2, s.y2)) for s in segs]

    # tees: an endpoint lying inside another segment splits it
    splits: dict[int, list[tuple[float, int]]] = defaultdict(list)
    seg_index = {id(s): i for i, s in enumerate(segs)}
    for n, (x, y) in enumerate(node_xy):
        for s in seg_grid.near(x, y, p.snap_tol):
            i = seg_index[id(s)]
            if n in seg_ends[i]:
                continue
            d, t = _point_seg_dist(x, y, s)
            if d <= p.snap_tol and 0.0 < t < 1.0:
                splits[i].append((t, n))
    edges: list[tuple[int, int, int]] = []  # (node a, node b, seg index)
    tee_nodes: set[int] = set()
    for i, (a, b) in enumerate(seg_ends):
        chain = [a] + [n for _t, n in sorted(splits.get(i, []))] + [b]
        tee_nodes.update(n for _t, n in splits.get(i, []))
        for u, v in zip(chain, chain[1:]):
            if u != v:
                edges.append((u, v, i))

    # runs: connected components, solid and dashed kept apart
    degree: dict[int, int] = defaultdict(int)
    for u, v, _i in edges:
        degree[u] += 1
        degree[v] += 1
    runs = []
    for dashed_flag in (False, True):
        sub = [(u, v, i) for u, v, i in edges if segs[i].dashed == dashed_flag]
        nodes_in = sorted({n for u, v, _ in sub for n in (u, v)})
        if not nodes_in:
            continue
        pos = {n: k for k, n in enumerate(nodes_in)}
        f2, u2 = _union_find(len(nodes_in))
        for u, v, _ in sub:
            u2(pos[u], pos[v])
        comp: dict[int, dict] = {}
        for u, v, i in sub:
            c = comp.setdefault(f2(pos[u]), {"nodes": set(), "segs": set()})
            c["nodes"].update((u, v))
            c["segs"].add(i)
        for c in comp.values():
            length = sum(segs[i].length for i in c["segs"])
            ends = sorted(n for n in c["nodes"] if degree[n] == 1)
            runs.append({"kind": "signal_candidate" if dashed_flag else "pipe_candidate",
                         "segments": sorted(c["segs"]), "nodes": sorted(c["nodes"]),
                         "ends": ends, "tees": sorted(n for n in c["nodes"] if n in tee_nodes),
                         "length": length})

    # what each run end touches
    def touches(x, y) -> list[str]:
        hit = [f"B{k}" for k, b in enumerate(boxes) if _near_rect(x, y, b, p.snap_tol * 2)]
        hit += [f"S{k}" for k, s in enumerate(symbols) if _near_rect(x, y, s["bbox"], p.snap_tol * 2)]
        return hit

    for r in runs:
        r["end_touches"] = {f"N{n}": touches(*node_xy[n]) for n in r["ends"]}
        mids = {t for n in r["nodes"] for t in touches(*node_xy[n])}
        r["touches"] = sorted(mids)

    # tags: attach tag-like text to the nearest thing
    tags = []
    for t in texts:
        txt = " ".join(t["text"].split())
        if not TAG_RE.match(txt.upper()):
            continue
        x0, y0, x1, y1 = t["bbox"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        best, best_d = None, p.tag_radius
        for k, b in enumerate(boxes):
            d = 0.0 if _near_rect(cx, cy, b, 0) else _rect_dist(cx, cy, b)
            if d < best_d:
                best, best_d = f"B{k}", d
        for k, s in enumerate(symbols):
            d = _rect_dist(cx, cy, s["bbox"])
            if d < best_d:
                best, best_d = f"S{k}", d
        if best is None:
            for s in seg_grid.near(cx, cy, p.tag_radius):
                d, _t = _point_seg_dist(cx, cy, s)
                if d < best_d:
                    i = seg_index[id(s)]
                    run = next((k for k, r in enumerate(runs) if i in r["segments"]), None)
                    if run is not None:
                        best, best_d = f"R{run}", d
        tags.append({"text": txt, "bbox": (x0, y0, x1, y1), "near": best,
                     "distance": None if best is None else round(best_d, 1)})

    return {"segments": segs, "nodes": node_xy, "tee_nodes": tee_nodes, "degree": degree,
            "runs": runs, "boxes": boxes, "symbols": symbols, "tags": tags,
            "stats": {"subpaths": len(subpaths), "raw_segments": len(raw_segs),
                      "merged_away": absorbed, "segments": len(segs),
                      "nodes": len(node_xy), "tees": len(tee_nodes),
                      "pipe_runs": sum(r["kind"] == "pipe_candidate" for r in runs),
                      "signal_runs": sum(r["kind"] == "signal_candidate" for r in runs),
                      "boxes": len(boxes), "symbols": len(symbols),
                      "filled_shapes_skipped": skipped_fill, "tags": len(tags)}}


def _rect_dist(x, y, r) -> float:
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


# ---------------------------------------------------------------- output

def _norm_point(x, y, w, h, rotation) -> list[float]:
    u, v = x / w, 1 - y / h
    if rotation == 90:
        u, v = 1 - v, u
    elif rotation == 180:
        u, v = 1 - u, 1 - v
    elif rotation == 270:
        u, v = v, 1 - u
    return [round(u, 5), round(v, 5)]


def _norm_rect(b, w, h, rotation) -> list[float]:
    a = _norm_point(b[0], b[1], w, h, rotation)
    c = _norm_point(b[2], b[3], w, h, rotation)
    return [min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])]


def skeleton_to_json(sk: dict, w: float, h: float, rotation: int) -> dict:
    segs = sk["segments"]
    seg_run = {i: k for k, r in enumerate(sk["runs"]) for i in r["segments"]}
    return {
        "page_size_pt": [round(w, 2), round(h, 2)],
        "stats": sk["stats"],
        "nodes": [{"id": f"N{k}", "xy": _norm_point(x, y, w, h, rotation),
                   "degree": sk["degree"].get(k, 0), "tee": k in sk["tee_nodes"]}
                  for k, (x, y) in enumerate(sk["nodes"])],
        "segments": [{"id": f"G{i}", "a": _norm_point(s.x1, s.y1, w, h, rotation),
                      "b": _norm_point(s.x2, s.y2, w, h, rotation),
                      "style": "dashed" if s.dashed else "solid", "width_pt": round(s.width, 2),
                      "run": f"R{seg_run[i]}" if i in seg_run else None}
                     for i, s in enumerate(segs)],
        "runs": [{"id": f"R{k}", "kind": r["kind"], "length_pt": round(r["length"], 1),
                  "segments": [f"G{i}" for i in r["segments"]],
                  "ends": [f"N{n}" for n in r["ends"]], "tees": [f"N{n}" for n in r["tees"]],
                  "touches": r["touches"], "end_touches": r["end_touches"]}
                 for k, r in enumerate(sk["runs"])],
        "boxes": [{"id": f"B{k}", "bbox": _norm_rect(b, w, h, rotation)} for k, b in enumerate(sk["boxes"])],
        "symbols": [{"id": f"S{k}", "bbox": _norm_rect(s["bbox"], w, h, rotation),
                     "parts": s["parts"], "hint": s["hint"]} for k, s in enumerate(sk["symbols"])],
        "tags": [{"text": t["text"], "bbox": _norm_rect(t["bbox"], w, h, rotation), "near": t["near"],
                  "distance_pt": t["distance"]} for t in sk["tags"]],
    }


class VectorGeometryReader:
    name = "vector_geometry"
    version = "0.1.0"
    applies_to = frozenset({"vector_text", "vector_outlined", "hybrid"})

    def __init__(self, params: Params | None = None):
        self.params = params or Params()

    def read(self, pdf_path: str, page_no: int, rotation: int = 0) -> ReaderResult:
        import pypdfium2 as pdfium
        import pypdfium2.raw as raw

        pdf = pdfium.PdfDocument(pdf_path)
        try:
            page = pdf[page_no - 1]
            w, h = page.get_size()
            handles = (raw.FPDFPage_GetObject(page.raw, i) for i in range(raw.FPDFPage_CountObjects(page.raw)))
            subpaths: list[dict] = []
            for obj, m in _iter_paths(raw, handles, IDENTITY):
                scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0
                width, dashed, stroked, filled = _style(raw, obj, scale)
                for sp in _subpaths(raw, obj, m):
                    sp.update(width=width, dashed=dashed, stroked=stroked, filled=filled)
                    subpaths.append(sp)
            texts = []
            tp = page.get_textpage()
            for i in range(tp.count_rects()):
                l, b, r, t = tp.get_rect(i)
                txt = (tp.get_text_bounded(l, b, r, t) or "").strip()
                if txt:
                    texts.append({"text": txt, "bbox": (l, b, r, t)})
        finally:
            pdf.close()

        sk = build_skeleton(subpaths, w, h, texts, self.params)
        data = skeleton_to_json(sk, w, h, rotation)
        warnings = []
        st = sk["stats"]
        if st["segments"] == 0:
            warnings.append("no straight vector segments: this page is probably a scan; use the raster route")
        if st["segments"] > self.params.max_segments:
            warnings.append(f"{st['segments']} segments: very dense page (hatching or outlined text?); trust runs less")
        if not texts:
            warnings.append("no text layer: tags not attached; join OCR hints from the seed's make_hints.py")
        return ReaderResult(self.name, self.version, page_no, data, warnings)
