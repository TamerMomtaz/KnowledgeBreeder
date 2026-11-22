"""Walk the plant: a plant graph drawn as one HTML file that opens with no internet.

    a line of items     the process, source on the left, sink on the right
    rows below it       branches: a standby pump, a second feed, a side stream
    circles above it    instruments, with a thin line to what they measure
    a dashed pipe       the flow direction was guessed by the reader, not drawn
    a dashed outline    the item was read with low confidence
    a number            how many items starve if this one stops
    ?                   kb has an open question about it

Pick an item, then ask "if it stops" or "to isolate it". Both answers are worked
out here for every item, by the same code as `kb whatif`, and the page only
shows them. Every item is also a button in a list, so the page works by
keyboard and without the drawing.

kb chose where things stand. Only the connections come from the drawing.

The file holds the plant. It asks the browser for nothing from the network, and
a content security policy in the page forbids it.
"""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import date
from importlib import resources
from pathlib import Path

from .. import theme
from ..graph import PlantGraph
from ..use import manipulation, research, statistics
from ..use.common import ISOLATION_KINDS, LEVEL_KINDS, PUMP_KINDS, attrs, instruments_near, is_equipment, kind, sheet
from .labels import LABELS
from .layout import Sketch, sketch

CW, PADX, PADY = 132, 74, 16            # column pitch, side and top margin
BELOW, ABOVE, BAND, R = 60, 44, 46, 17  # room under a row, over it, per ring of instruments, and the ring's radius
LOW = 0.7                               # the same line research.py draws for "read with low confidence"
BOARD = {"dcs", "panel", "control_room", "board"}


def shape(pg: PlantGraph, n: str, ways: int = 1) -> tuple[str, int, int]:
    """The glyph for an item, and its width and height."""
    d = pg.node(n)
    t, k = d.get("type"), kind(pg, n)
    if t == "Boundary":
        return "edge", 60, 28
    if t == "Equipment":
        return ("pump", 42, 42) if k in PUMP_KINDS else ("tank", 52, 68) if k in LEVEL_KINDS else ("box", 58, 42)
    if t == "Component":
        if k == "control_valve":
            return "cvalve", 34, 22
        return ("valve", 34, 22) if "valve" in k or k in ISOLATION_KINDS else ("part", 26, 26)
    if t == "Instrument":
        return "inline", 30, 30
    return "joint", 8, 10 + 10 * max(ways - 1, 0)


def shown(pg: PlantGraph, n: str) -> str:
    return re.sub(r"^BOUNDARY:\s*", "", pg.label(n), flags=re.I)


def _plain(x):
    """The same text, list or dict with the 'BOUNDARY:' prefix of boundary names taken off, for showing."""
    if isinstance(x, str):
        return re.sub(r"\bBOUNDARY:\s*", "", x, flags=re.I)
    if isinstance(x, list):
        return [_plain(v) for v in x]
    return {k: _plain(v) for k, v in x.items()} if isinstance(x, dict) else x


def _short(text: str, limit: int = 17) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _f(*nums: float) -> str:
    return ",".join(f"{v:.1f}".rstrip("0").rstrip(".") for v in nums)


def _glyph(name: str, x: float, y: float, w: int, h: int, text: str = "") -> str:
    if name == "tank":
        return f'<rect class="g" x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w}" height="{h}" rx="14"/>'
    if name == "pump":
        return (f'<circle class="g" cx="{x:.1f}" cy="{y:.1f}" r="{w / 2:.1f}"/>'
                f'<path class="in" d="M{_f(x - 7, y - 10)}L{_f(x + 11, y)}L{_f(x - 7, y + 10)}z"/>')
    if name == "box":
        return f'<rect class="g" x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w}" height="{h}" rx="4"/>'
    if name in ("valve", "cvalve"):
        bow = f'<path class="g" d="M{_f(x - 17, y - 11)}L{_f(x + 17, y + 11)}V{y - 11:.1f}L{_f(x - 17, y + 11)}z"/>'
        if name == "valve":
            return bow
        return (f'<path class="stem" d="M{_f(x, y)}v-14"/>'
                f'<path class="g" d="M{_f(x - 10, y - 14)}a10,10 0 0 1 20,0z"/>' + bow)
    if name == "part":
        return f'<path class="g" d="M{_f(x, y - 13)}L{_f(x + 13, y)}L{_f(x, y + 13)}L{_f(x - 13, y)}z"/>'
    if name == "inline":
        return (f'<circle class="g" cx="{x:.1f}" cy="{y:.1f}" r="14"/>'
                f'<text class="bt" x="{x:.1f}" y="{y + 3.2:.1f}" text-anchor="middle">{html.escape(text)}</text>')
    if name == "edge":
        return (f'<path class="g" d="M{_f(x - 30, y - 14)}H{x + 17:.1f}L{_f(x + 30, y)}L{_f(x + 17, y + 14)}'
                f'H{x - 30:.1f}z"/>')
    return f'<rect class="g jt" x="{x - 4:.1f}" y="{y - h / 2:.1f}" width="8" height="{h}" rx="4"/>'


def _tag_parts(tag: str) -> tuple[str, str]:
    """'FIT-0502' -> FIT, 0502. The two lines inside an instrument circle."""
    m = re.match(r"^([A-Za-z]+)[-_ ]?(.*)$", tag)
    return (m.group(1), m.group(2)) if m else (tag, "")


class _Drawing:
    """Places, sizes and the SVG for one plant."""

    def __init__(self, pg: PlantGraph, sk: Sketch):
        self.pg, self.sk = pg, sk
        self.key: dict[str, str] = {}                   # node id -> the short key used in the page
        self.pos: dict[str, tuple[float, float]] = {}
        self.size: dict[str, tuple[str, int, int]] = {}
        self.bubble: dict[str, tuple[float, float]] = {}
        self.paths: dict[int, list[tuple[float, float]]] = {}
        self._place_instruments()
        self._rows()
        self._route()
        self._place_bubbles()
        self._place_loose()
        for n in [*self.sk.items, *self.sk.loose, *sorted(self.bubble)]:
            self.key.setdefault(n, f"i{len(self.key)}")

    # ---- instruments off the line -------------------------------------------------------------------------
    def _place_instruments(self):
        pg, sk = self.pg, self.sk
        drawn = set(sk.items)
        off = [i for i in sorted(pg.of_type("Instrument")) if i not in drawn and i not in sk.loose]
        self.anchor: dict[str, tuple] = {}              # instrument -> ("node", id) or ("line", index)
        self.level: dict[str, int] = {}
        for i in off:
            for t in pg.out(i, "MEASURES"):
                if t in drawn:
                    self.anchor[i], self.level[i] = ("node", t), 1
                    break
                if t in sk.carrier:
                    self.anchor[i], self.level[i] = ("line", sk.carrier[t]), 1
                    break
        self.near: dict[str, list[str]] = {}            # an instrument that measures nothing: who it talks to
        changed = True
        while changed:
            changed = False
            for i in off:
                if i in self.level:
                    continue
                talk = sorted({*pg.out(i, "SIGNAL_TO"), *pg.into(i, "SIGNAL_TO"), *pg.out(i, "ACTUATES")})
                known = [n for n in talk if n in drawn or n in self.level]
                if known:
                    self.near[i], self.level[i], changed = known, 2, True
        self.adrift = [i for i in off if i not in self.level]

    def _line_spot(self, k: int) -> tuple[int, float]:
        """Row and column (in column units) of the middle of a line's longest level stretch."""
        ln = self.sk.lines[k]
        pts = [ln.u, *ln.way, ln.v]
        if ln.back:
            return self.sk.row[ln.u], self.sk.col[ln.u] + 0.3
        runs: list[list[float]] = []                    # [row, from, to]
        for a, b in zip(pts, pts[1:]):
            ca, ra, rb = self.sk.col[a], self.sk.row[a], self.sk.row[b]
            for r, c0, c1 in ((ra, ca, ca + 0.5), (rb, ca + 0.5, ca + 1)):
                if runs and runs[-1][0] == r and abs(runs[-1][2] - c0) < 1e-9:
                    runs[-1][2] = c1
                else:
                    runs.append([r, c0, c1])
        r, c0, c1 = max(runs, key=lambda x: x[2] - x[1])
        return int(r), (c0 + c1) / 2

    def _spot(self, i: str, seen: frozenset = frozenset()) -> tuple[int, float]:
        """Row and column an off-line instrument belongs over."""
        if i in self.anchor:
            what, ref = self.anchor[i]
            return (self.sk.row[ref], float(self.sk.col[ref])) if what == "node" else self._line_spot(ref)
        spots = [(self.sk.row[n], float(self.sk.col[n])) if n in self.sk.col else self._spot(n, seen | {i})
                 for n in self.near.get(i, []) if n not in seen]
        if not spots:
            return 0, 0.0
        return spots[0][0], sum(s[1] for s in spots) / len(spots)

    # ---- rows ---------------------------------------------------------------------------------------------
    def _rows(self):
        sk = self.sk
        self.spot = {i: self._spot(i) for i in self.level}
        rings = defaultdict(int)
        for i, (r, _c) in self.spot.items():
            rings[r] = max(rings[r], self.level[i])
        self.rows = max(sk.row.values(), default=-1) + 1
        self.rowy: dict[int, float] = {}
        y = PADY
        for r in range(self.rows):
            y += ABOVE + BAND * rings[r]
            self.rowy[r] = y
            y += BELOW
        self.bottom = y
        ways = defaultdict(lambda: [0, 0])
        for ln in sk.lines:
            ways[ln.u][0] += 1
            ways[ln.v][1] += 1
        for n in sk.items:
            self.size[n] = shape(self.pg, n, max(ways[n]))
            self.pos[n] = (PADX + sk.col[n] * CW, self.rowy[sk.row[n]])
        for n in sk.col:
            if n.startswith("~"):
                self.pos[n] = (PADX + sk.col[n] * CW, self.rowy[sk.row[n]])

    # ---- pipes --------------------------------------------------------------------------------------------
    def _route(self):
        sk = self.sk
        outs, ins = defaultdict(list), defaultdict(list)
        for k, ln in enumerate(sk.lines):
            if ln.back:
                outs[ln.u].append((k, None))
                ins[ln.v].append((k, None))
            else:
                pts = [ln.u, *ln.way, ln.v]
                outs[ln.u].append((k, sk.row[pts[1]] - sk.row[ln.u]))
                ins[ln.v].append((k, sk.row[pts[-2]] - sk.row[ln.v]))

        def spread(n, ends):
            """Each line gets its own height on the item: level lines in the middle, the others stacked to their side."""
            below = sorted((e for e in ends if e[1] is not None and e[1] > 0), key=lambda e: e[1])
            below += [e for e in ends if e[1] is None]
            above = sorted((e for e in ends if e[1] is not None and e[1] < 0), key=lambda e: -e[1])
            most = max(len(below), len(above), 1)
            step = min(11.0, (self.size[n][2] / 2 - 3) / most)
            out = {k: 0.0 for k, d in ends if d == 0}
            out.update({k: (j + 1) * step for j, (k, _d) in enumerate(below)})
            out.update({k: -(j + 1) * step for j, (k, _d) in enumerate(above)})
            return out
        out_at = {n: spread(n, e) for n, e in outs.items()}
        in_at = {n: spread(n, e) for n, e in ins.items()}

        turns = defaultdict(list)                       # column gap -> the hops that change row in it
        for k, ln in enumerate(sk.lines):
            if ln.back:
                continue
            pts = [ln.u, *ln.way, ln.v]
            for j, (a, b) in enumerate(zip(pts, pts[1:])):
                if sk.row[a] != sk.row[b]:
                    turns[sk.col[a]].append((min(sk.row[a], sk.row[b]), max(sk.row[a], sk.row[b]), k, j))
        track = {}
        for c, hops in turns.items():
            hops.sort()
            step = min(9.0, 50 / max(len(hops) - 1, 1))
            for j, (_lo, _hi, k, hop) in enumerate(hops):
                track[k, hop] = PADX + (c + 0.5) * CW + (j - (len(hops) - 1) / 2) * step

        loops = 0
        for k, ln in enumerate(sk.lines):
            (xu, yu), (xv, yv) = self.pos[ln.u], self.pos[ln.v]
            start = (xu + self.size[ln.u][1] / 2, yu + out_at[ln.u][k])
            end = (xv - self.size[ln.v][1] / 2 - 1, yv + in_at[ln.v][k])
            if ln.back:
                x1, x2 = start[0] + 12 + loops * 5, end[0] - 14 - loops * 5
                yb = self.bottom + 12 + loops * 10
                self.paths[k] = [start, (x1, start[1]), (x1, yb), (x2, yb), (x2, end[1]), end]
                loops += 1
                continue
            pts = [start, *(self.pos[d] for d in ln.way), end]
            path = [start]
            for j, (a, b) in enumerate(zip(pts, pts[1:])):
                if abs(a[1] - b[1]) > 0.01:
                    tx = track.get((k, j), (a[0] + b[0]) / 2)
                    path += [(tx, a[1]), (tx, b[1])]
                path.append(b)
            self.paths[k] = path
        self.bottom += loops * 10 + (14 if loops else 0)

    def _on_line(self, k: int, r: int, x: float) -> tuple[float, float]:
        """The point of line k nearest to x on its level stretch in row r."""
        best = None
        for a, b in zip(self.paths[k], self.paths[k][1:]):
            if abs(a[1] - b[1]) < 0.01 and abs(a[1] - self.rowy[r]) <= 16:
                lo, hi = sorted((a[0], b[0]))
                px = min(max(x, lo), hi)
                if best is None or abs(px - x) < abs(best[0] - x):
                    best = (px, a[1])
        return best or (x, self.rowy[r])

    # ---- instrument circles -------------------------------------------------------------------------------
    def _place_bubbles(self):
        bands = defaultdict(list)
        for i, (r, c) in self.spot.items():
            bands[r, self.level[i]].append((PADX + c * CW, i))
        gap = 2 * R + 6
        for (r, lev), items in bands.items():
            items.sort()
            xs = []
            for want, _i in items:
                xs.append(max(want, xs[-1] + gap) if xs else want)
            j = 0
            while j < len(xs):                          # a pushed group is centred back over what it measures
                e = j
                while e + 1 < len(xs) and xs[e + 1] - xs[e] < gap + 0.01:
                    e += 1
                shift = sum(xs[m] - items[m][0] for m in range(j, e + 1)) / (e - j + 1)
                floor = xs[j - 1] + gap if j else R + 4
                shift = min(shift, xs[j] - floor)
                for m in range(j, e + 1):
                    xs[m] -= max(shift, 0)
                j = e + 1
            y = self.rowy[r] - ABOVE - BAND * (lev - 1) - R - 3
            for x, (_want, i) in zip(xs, items):
                self.bubble[i] = (x, y)

    def _place_loose(self):
        cols = max(max((self.sk.col[n] for n in self.sk.items), default=0) + 1, 6)
        self.loose_y = None
        loose = [*self.sk.loose, *self.adrift]
        if loose:
            self.loose_y = self.bottom + 26
            for j, n in enumerate(loose):
                x, y = PADX + (j % cols) * CW, self.loose_y + 70 + (j // cols) * 96
                if n in self.adrift:
                    self.bubble[n] = (x, y)
                else:
                    self.size[n] = shape(self.pg, n)
                    self.pos[n] = (x, y)
            self.bottom = self.loose_y + 70 + ((len(loose) - 1) // cols) * 96 + BELOW
        xs = [x for x, _y in self.pos.values()] + [x for x, _y in self.bubble.values()]
        self.width = max(xs, default=PADX) + PADX
        self.height = self.bottom + 6

    # ---- drawing ------------------------------------------------------------------------------------------
    def _top(self, n: str) -> tuple[float, float]:
        """Where a signal or a measuring line meets a drawn item."""
        x, y = self.pos[n]
        name, _w, h = self.size[n]
        return (x, y - 24) if name == "cvalve" else (x, y - h / 2)

    def _end(self, n: str, toward: tuple[float, float]) -> tuple[float, float]:
        if n in self.bubble:
            (x, y), r = self.bubble[n], R
        elif n in self.pos and self.size[n][0] == "inline":
            (x, y), r = self.pos[n], 14
        elif n in self.pos:
            return self._top(n)
        else:
            return toward
        dx, dy = toward[0] - x, toward[1] - y
        d = (dx * dx + dy * dy) ** 0.5 or 1
        return x + dx / d * r, y + dy / d * r

    def _centre(self, n: str) -> tuple[float, float] | None:
        if n in self.bubble:
            return self.bubble[n]
        return self._top(n) if n in self.pos and self.size[n][0] != "inline" else self.pos.get(n)

    def svg(self, marks: dict[str, dict]) -> str:
        pg, sk, out = self.pg, self.sk, []
        for k, ln in enumerate(sk.lines):
            p = self.paths[k]
            (xe, ye) = p[-1]
            d = "M" + "L".join(_f(x, y) for x, y in [*p[:-1], (xe - 5, ye)])
            cls = "e" + (" inf" if ln.inferred else "") + (" back" if ln.back else "")
            out.append(f'<g class="{cls}" data-u="{self.key[ln.u]}" data-v="{self.key[ln.v]}"><path class="pl" d="{d}"/>'
                       f'<path class="ah" d="M{_f(xe, ye)}L{_f(xe - 7, ye - 3.5)}V{ye + 3.5:.1f}z"/></g>')
        for i, (what, ref) in sorted(self.anchor.items()):
            bx, by = self.bubble[i]
            ax, ay = self._top(ref) if what == "node" else self._on_line(ref, self.spot[i][0], bx)
            out.append(f'<path class="lead" d="M{_f(bx, by + R)}L{_f(ax, ay)}"/>')
        done = set()
        for etype in ("SIGNAL_TO", "ACTUATES"):
            for a, b, _d in pg.edges(etype):
                ca, cb = self._centre(a), self._centre(b)
                if ca is None or cb is None or (a, b) in done:
                    continue
                done.add((a, b))
                (x1, y1), (x2, y2) = self._end(a, cb), self._end(b, ca)
                out.append(f'<path class="sig" d="M{_f(x1, y1)}L{_f(x2, y2)}"/>')
        if self.loose_y is not None:
            out.append(f'<path class="rule" d="M{_f(PADX - 40, self.loose_y)}H{self.width - PADX + 40:.1f}"/>'
                       f'<text class="cap" data-i18n="loose" x="{PADX - 40}" y="{self.loose_y + 16:.1f}"></text>')
        labels = []
        for n in [*sk.items, *sk.loose]:
            (x, y), (name, w, h) = self.pos[n], self.size[n]
            d, m, tag = pg.node(n), marks.get(n, {}), shown(pg, n)
            text = _tag_parts(tag)[0][:4] if name == "inline" else ""
            body = (f'<rect class="hit" x="{x - max(w, 44) / 2:.1f}" y="{y - max(h, 44) / 2:.1f}" '
                    f'width="{max(w, 44)}" height="{max(h, 44)}"/>' + _glyph(name, x, y, w, h, text))
            if m.get("starves"):
                bx, by, bw = x - w / 2 - 2, y - h / 2 - 2, 10 + 6 * len(str(m["starves"]))
                body += (f'<g class="sp"><rect x="{bx - bw / 2:.1f}" y="{by - 8:.1f}" width="{bw}" height="16" rx="8"/>'
                         f'<text x="{bx:.1f}" y="{by + 3.4:.1f}" text-anchor="middle">{m["starves"]}</text></g>')
            if m.get("asked"):
                body += f'<text class="qm" x="{x + w / 2 + 3:.1f}" y="{y - h / 2 + 2:.1f}">?</text>'
            cls = f"n k-{name}" + (" lowc" if (d.get("confidence") or 1) < LOW else "")
            out.append(f'<g class="{cls}" id="n-{self.key[n]}" data-id="{self.key[n]}" tabindex="0" role="button" '
                       f'aria-label="{html.escape(tag, quote=True)}"><title>{html.escape(tag)}</title>{body}</g>')
            if name != "joint":
                labels.append(f'<text class="lb" data-for="{self.key[n]}" x="{x:.1f}" y="{y + h / 2 + 14:.1f}" '
                              f'text-anchor="middle">{html.escape(_short(tag))}</text>')
        for i in sorted(self.bubble):
            (x, y), d, tag = self.bubble[i], pg.node(i), shown(pg, i)
            top, low = _tag_parts(tag)
            body = f'<rect class="hit" x="{x - 22:.1f}" y="{y - 22:.1f}" width="44" height="44"/>'
            where = str(attrs(pg, i).get("location") or "").lower()
            if where == "dcs":
                body += f'<rect class="g" x="{x - R:.1f}" y="{y - R:.1f}" width="{2 * R}" height="{2 * R}"/>'
            body += f'<circle class="g" cx="{x:.1f}" cy="{y:.1f}" r="{R}"/>'
            if where in BOARD:
                body += f'<path class="stem" d="M{_f(x - R, y)}h{2 * R}"/>'
            body += (f'<text class="bt" x="{x:.1f}" y="{y - 2:.1f}" text-anchor="middle">{html.escape(top[:5])}</text>'
                     f'<text class="bt" x="{x:.1f}" y="{y + 9:.1f}" text-anchor="middle">{html.escape(low[:6])}</text>')
            if marks.get(i, {}).get("asked"):
                body += f'<text class="qm" x="{x + R + 1:.1f}" y="{y - R + 4:.1f}">?</text>'
            cls = "n bub" + (" lowc" if (d.get("confidence") or 1) < LOW else "")
            out.append(f'<g class="{cls}" id="n-{self.key[i]}" data-id="{self.key[i]}" tabindex="0" role="button" '
                       f'aria-label="{html.escape(tag, quote=True)}"><title>{html.escape(tag)}</title>{body}</g>')
        return (f'<svg id="plant" class="plant" viewBox="0 0 {self.width:.0f} {self.height:.0f}" '
                f'width="{self.width:.0f}" height="{self.height:.0f}" role="group">{"".join(out)}{"".join(labels)}</svg>')


def _value(v) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return "yes" if v is True else "no" if v is False else str(v)


def build(pg: PlantGraph, title: str | None = None, lang: str = "en", today: date | None = None) -> str:
    """The whole page as one string."""
    today = today or date.today()
    lang = lang if lang in LABELS else "en"
    flow = pg.flow()
    sk = sketch(pg, flow)
    dr = _Drawing(pg, sk)
    key = dr.key

    def keys(ids) -> list[str]:
        return [key[n] for n in sorted(ids, key=lambda n: (pg.label(n), n)) if n in key]

    questions = []
    asked = defaultdict(list)
    for qi, q in enumerate(research.questions(pg)):
        found = []
        for part in re.split(r"\s*/\s*|\s*,\s*", q["subject"]):
            try:
                nid = pg.find(part)
            except KeyError:
                continue
            if nid in key and nid not in found:
                found.append(nid)
                asked[nid].append(qi)
        questions.append({**_plain(q), "keys": [key[n] for n in found]})
    spof = manipulation.single_points(pg, top=10 ** 6)
    starves = {pg.find(r["tag"]): r["starves"] for r in spof}
    spof = [{**_plain(r), "key": key.get(pg.find(r["tag"]))} for r in spof]
    marks = {n: {"starves": starves.get(n), "asked": bool(asked.get(n))} for n in key}

    loops = []
    loop_at = {}
    for l in sorted(pg.of_type("ControlLoop")):
        a = attrs(pg, l)
        text = a.get("description") or (f"{', '.join(a.get('controllers') or ['?'])} acts on "
                                        f"{', '.join(a.get('final_elements') or ['nothing drawn'])}")
        loop_at[l] = len(loops)
        loops.append({"name": pg.label(l), "kind": a.get("loop_type") or "", "variable": a.get("variable") or "",
                      "text": text, "members": keys(m for m, _role in pg.loop_members(l))})

    ctx = manipulation.context(pg)
    up, down = defaultdict(list), defaultdict(list)
    for ln in sk.lines:
        if ln.u != ln.v:
            down[ln.u].append(ln.v)
            up[ln.v].append(ln.u)

    def beside(n, others):
        r = sk.row.get(n, 0)
        return [key[m] for m in sorted(set(others), key=lambda m: (sk.row[m] != r, sk.row[m], sk.col[m], m))]

    nodes = {}
    for n, k in key.items():
        d = pg.node(n)
        x, y = dr.pos[n] if n in dr.pos else dr.bubble[n]
        f = manipulation.fail_sets(pg, n, ctx)
        iso = manipulation.isolate_sets(pg, n, flow)
        near = instruments_near(pg, flow, n) if d.get("type") == "Equipment" and n in flow else pg.measured_by(n)
        a = attrs(pg, n)
        nodes[k] = {
            "name": shown(pg, n), "id": n, "type": d.get("type") or "", "kind": kind(pg, n).replace("_", " "),
            "dir": a.get("direction") or "", "sheet": sheet(pg, n) or "", "conf": d.get("confidence"),
            "low": (d.get("confidence") or 1) < LOW, "x": round(x), "y": round(y),
            "c": sk.col.get(n, -1), "r": sk.row.get(n, -1),
            "up": beside(n, up[n]), "down": beside(n, down[n]),
            "near": keys(i for i in near if i != n), "measures": [
                {"k": key.get(t), "name": shown(pg, t)} for t in pg.out(n, "MEASURES")],
            "to": keys(pg.out(n, "SIGNAL_TO")), "from": keys(pg.into(n, "SIGNAL_TO")),
            "loops": [loop_at[l] for l in pg.loops_of(n) if l in loop_at],
            "attrs": [[str(kk).replace("_", " "), _value(v)] for kk, v in sorted(a.items()) if v not in (None, "", [])],
            "q": asked.get(n, []),
            "fail": {"lost": keys(f["lost"]), "other": len([m for m in f["lost"] if not is_equipment(pg, m)]),
                     "spared": keys(f["spared"]), "blind": keys(f["blind"]),
                     "loops": [loop_at[l] for l in f["loops"] if l in loop_at]},
            "iso": None if iso is None else {"close": keys(iso["valves"]), "open": keys(iso["open_ends"]),
                                             "inside": keys(iso["inside"])},
        }
    st = statistics.stats(pg)
    order = [key[n] for n in [*sk.items, *sk.loose]] + keys(dr.bubble)
    plant = (pg.data.get("plant") or {}).get("name") or ""
    data = {"lang": lang, "today": today.isoformat(), "title": title or plant, "labels": LABELS, "nodes": nodes,
            "order": order, "loops": loops, "spof": spof, "questions": questions, "w": round(dr.width),
            "counts": {"items": len(sk.items) + len(sk.loose),
                       "instruments": len(pg.of_type("Instrument")), "loops": len(loops), "questions": len(questions)},
            "stats": _plain({"by_type": st["size"]["by_type"], "equipment": st["equipment_by_kind"],
                             "instruments": st["instruments_by_variable"], "sources": st["topology"]["sources"],
                             "sinks": st["topology"]["sinks"], "longest": st["topology"]["longest_path"],
                             "mean_conf": st["trust"]["mean_confidence"], "low": st["trust"]["nodes_below_0.7"],
                             "inferred": st["trust"]["inferred_flow_share"]})}
    names = "".join(
        f'<li><button type="button" class="pick" data-id="{k}"><bdi>{html.escape(nodes[k]["name"])}</bdi></button></li>'
        for k in order)
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")     # plant text can never close the script
    page = resources.files(__package__).joinpath("plant.html").read_text(encoding="utf-8")
    head = html.escape(title or plant or LABELS[lang]["title"])
    return theme.inject(page.replace("__LANG__", lang).replace("__DIR__", "rtl" if lang == "ar" else "ltr")
                        .replace("__TITLE__", head).replace("<!--__PLANT__-->", dr.svg(marks))
                        .replace("<!--__NAMES__-->", names).replace("/*__DATA__*/", blob))


def write(pg: PlantGraph, path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build(pg, **kw), encoding="utf-8")
    return p
