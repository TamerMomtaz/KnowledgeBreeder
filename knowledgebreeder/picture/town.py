"""The town: a picture drawn as districts and buildings, in one HTML file that opens with no internet.

    district            an area of the person's life or work
    building            a project
    height              how many other projects it is tied to
    lit windows         worked on lately (the reader of the page picks how lately)
    flag on the roof    a decision is waiting
    crane on the roof   something was started and not finished
    empty lot           an area that was named but never described

The drawing is plain SVG made here, so it costs a phone nothing to show: no
animation loop, no 3D engine, no outside file. The page holds a small script
for picking, filtering and the reports. Every project is also a button in a
list under its district, so the page works by keyboard and without the drawing.

The file holds the person's own picture. It asks the browser for nothing from
the network, and a content security policy in the page forbids it.
"""

from __future__ import annotations

import html
import json
import math
import re
from datetime import date
from importlib import resources
from pathlib import Path

from .. import theme
from . import reports
from .cards import by_what, met
from .store import Picture

TW, TH, FLOOR, HALF, PAD, SLAB = 120, 60, 12, 0.3, 0.32, 9
MAX_FLOORS = 8
HUES = (208, 28, 152, 276, 46, 332, 96, 184)

LABELS = {
    "en": {
        "title": "The whole picture", "sub": "{n} projects in {a} areas. Newest work: {d}.",
        "lit": "Lit windows: worked on in the last", "days": "{n} days", "search": "Find a project",
        "themes": "The same idea in more than one project", "clear": "Clear",
        "legend_h": "Taller: tied to more projects", "legend_f": "Flag: a decision is waiting",
        "legend_c": "Crane: started and not finished", "legend_l": "Lit: worked on lately",
        "pick": "Pick a building to read its card.", "close": "Close",
        "can_do": "Can do", "exists": "What exists", "needs": "Needs", "unfinished": "Not finished",
        "ideas": "Ideas not started", "parts": "Parts that could travel", "links": "Tied to", "named_in": "Named by other cards",
        "themes_h": "Ideas it keeps returning to", "decisions": "Decisions waiting on you",
        "unseen": "What the card's writer could not see", "unknown": "Left as unknown",
        "last": "Last work", "no_date": "no date given", "goal": "Goal", "problem": "What it is for",
        "serves": "Who it serves", "met_yes": "met", "met_partly": "partly met", "met_no": "not met",
        "met_unknown": "not known if met", "no_card": "no card yet",
        "empty_lot": "Nothing told yet", "projects": "projects",
        "tab_brief": "Brief", "tab_overlaps": "Overlaps", "tab_gaps": "Gaps", "tab_reuse": "Reuse",
        "note": "Counted and word-matched from your own cards. A word match is a hint to look, not a finding.",
        "brief_note": "Moves worth a look, from rules over your own cards. It does not look outside the picture.",
        "why": "Why", "from": "From", "none": "Nothing here yet.",
        "o_themes": "The same idea in more than one project", "o_stated": "Overlaps the cards state themselves",
        "o_similar": "Described in similar words (word match)",
        "g_needs": "Needs not met", "g_unfinished": "Started and not finished", "g_decisions": "Decisions waiting on you",
        "g_named": "Named in a card, but no card of its own", "g_empty": "Areas with no card",
        "g_unclear": "A name that fits more than one card", "could_be": "could be",
        "g_alone": "Tied to nothing else", "g_quiet": "Quiet for more than {n} days", "g_unknown": "Left as unknown",
        "r_named": "A part one card offers to a named project", "r_matched": "A part that may answer a need elsewhere (word match)",
        "r_wide": "Parts offered to everything", "named_by": "named by", "show": "Show in the town",
        "private": "This file holds your picture. It makes no network requests.", "made": "Made {d} with kb picture town.",
    },
    "ar": {
        "title": "الصورة الكاملة",
        "sub": "{n} مشروع في {a} مجالات. أحدث عمل: {d}.",
        "lit": "النوافذ المضيئة: عمل خلال آخر",
        "days": "{n} يوم", "search": "ابحث عن مشروع",
        "themes": "نفس الفكرة في أكثر من مشروع",
        "clear": "مسح",
        "legend_h": "الأعلى: مرتبط بمشاريع أكثر",
        "legend_f": "العلم: قرار في الانتظار",
        "legend_c": "الرافعة: عمل بدأ ولم يكتمل",
        "legend_l": "مضيء: عمل عليه مؤخراً",
        "pick": "اختر مبنى لتقرأ بطاقته.",
        "close": "إغلاق",
        "can_do": "ما يستطيع فعله", "exists": "ما هو موجود",
        "needs": "ما يحتاجه", "unfinished": "غير مكتمل",
        "ideas": "أفكار لم تبدأ",
        "parts": "أجزاء تصلح لمشاريع أخرى",
        "links": "مرتبط بـ", "named_in": "تذكره بطاقات أخرى", "themes_h": "أفكار يعود إليها",
        "decisions": "قرارات في انتظارك",
        "unseen": "ما لم يره كاتب البطاقة",
        "unknown": "متروك كمجهول", "last": "آخر عمل",
        "no_date": "بدون تاريخ", "goal": "الهدف",
        "problem": "الغرض منه", "serves": "يخدم من",
        "met_yes": "متحقق", "met_partly": "متحقق جزئياً",
        "met_no": "غير متحقق", "met_unknown": "غير معروف",
        "no_card": "بدون بطاقة بعد",
        "empty_lot": "لم يُحكَ عنه شيء بعد",
        "projects": "مشاريع",
        "tab_brief": "الخلاصة", "tab_overlaps": "التكرار",
        "tab_gaps": "الفجوات", "tab_reuse": "إعادة الاستخدام",
        "note": "محسوب بالعدّ ومطابقة الكلمات من بطاقاتك. مطابقة الكلمات إشارة للنظر وليست نتيجة.",
        "brief_note": "خطوات تستحق النظر، من قواعد على بطاقاتك فقط. لا تنظر خارج الصورة.",
        "why": "السبب", "from": "المصدر",
        "none": "لا شيء هنا بعد.",
        "o_themes": "نفس الفكرة في أكثر من مشروع",
        "o_stated": "تكرار تذكره البطاقات نفسها",
        "o_similar": "وصف بكلمات متشابهة (مطابقة كلمات)",
        "g_needs": "احتياجات غير متحققة",
        "g_unfinished": "بدأ ولم يكتمل",
        "g_decisions": "قرارات في انتظارك",
        "g_named": "مذكور في بطاقة وليس له بطاقة",
        "g_empty": "مجالات بلا بطاقات",
        "g_unclear": "اسم ينطبق على أكثر من بطاقة", "could_be": "قد يكون",
        "g_alone": "غير مرتبط بشيء آخر",
        "g_quiet": "هادئ منذ أكثر من {n} يوم",
        "g_unknown": "متروك كمجهول",
        "r_named": "جزء تعرضه بطاقة على مشروع مسمى",
        "r_matched": "جزء قد يلبي احتياجاً في مكان آخر (مطابقة كلمات)",
        "r_wide": "أجزاء معروضة على الجميع",
        "named_by": "ذكره", "show": "أظهره في المدينة",
        "private": "هذا الملف يحمل صورتك ولا يتصل بأي شبكة.",
        "made": "صُنع في {d} بـ kb picture town.",
    },
}


def short(name: str, limit: int = 18) -> str:
    s = re.split(r"\s*[,(]", name.strip(), maxsplit=1)[0].strip() or name.strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def iso(x: float, y: float, z: float = 0.0) -> tuple[float, float]:
    return ((x - y) * TW / 2, (x + y) * TH / 2 - z)


def _pts(points) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _floors(degree: int) -> int:
    return 1 + min(degree, MAX_FLOORS - 1)


def _building(card: dict, i: int, j: int, floors: int) -> tuple[str, str, list[tuple[float, float]]]:
    """One building as SVG, its label as SVG, and the points it reaches (for the frame)."""
    cx, cy, h, s = i + 0.5, j + 0.5, floors * FLOOR, HALF
    a, b, c, d = (cx - s, cy + s), (cx + s, cy + s), (cx + s, cy - s), (cx - s, cy - s)
    g = [f'<polygon class="wl" points="{_pts([iso(*a), iso(*b), iso(*b, h), iso(*a, h)])}"/>',
         f'<polygon class="wr" points="{_pts([iso(*b), iso(*c), iso(*c, h), iso(*b, h)])}"/>',
         f'<polygon class="rf" points="{_pts([iso(*a, h), iso(*b, h), iso(*c, h), iso(*d, h)])}"/>']
    for k in range(floors):
        z0, z1 = k * FLOOR + 3, k * FLOOR + 9
        for p, q in ((a, b), (b, c)):
            for u0, u1 in ((0.16, 0.40), (0.60, 0.84)):
                p0 = (p[0] + (q[0] - p[0]) * u0, p[1] + (q[1] - p[1]) * u0)
                p1 = (p[0] + (q[0] - p[0]) * u1, p[1] + (q[1] - p[1]) * u1)
                g.append(f'<polygon class="wn" points="{_pts([iso(*p0, z0), iso(*p1, z0), iso(*p1, z1), iso(*p0, z1)])}"/>')
    if card["decisions"]:
        x, y = iso(cx - 0.11, cy + 0.11, h)
        g.append(f'<path class="flag" d="M{x:.1f},{y:.1f}v-17l11,4l-11,4"/>')
    if card["unfinished"]:
        x, y = iso(cx + 0.13, cy - 0.13, h)
        g.append(f'<path class="crane" d="M{x:.1f},{y:.1f}v-15h13m-13,0l-5,3m12,-3v5"/>')
    lx, ly = iso(cx, cy, h)
    ly -= TH * s + 5                                  # just above the roof's far corner, clear of flag and crane
    name = html.escape(card["name"], quote=True)
    cls = "b" + (" has-flag" if card["decisions"] else "") + (" has-crane" if card["unfinished"] else "")
    body = (f'<g class="{cls}" id="b-{card["id"]}" data-id="{card["id"]}" data-last="{card.get("last_date") or ""}" '
            f'tabindex="0" role="button" aria-label="{name}"><title>{name}</title>{"".join(g)}</g>')
    label = (f'<text class="lb" data-for="{card["id"]}" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle">'
             f'{html.escape(short(card["name"]))}</text>')
    reach = [iso(*a), iso(*c), iso(*b), (lx - 62, ly - 12), (lx + 62, ly)]
    return body, label, reach


def district_svg(area: str, cards: list[dict], degree: dict[str, int]) -> str:
    """One district: a slab of ground with its buildings, tallest at the back so no label is hidden."""
    n = len(cards)
    rows = 1 if n <= 3 else 2 if n <= 10 else 3 if n <= 18 else math.ceil(math.sqrt(n / 2))   # wide, not deep
    cols = max(1, math.ceil(n / rows)) if n else 2
    cells = sorted(((i, j) for j in range(rows) for i in range(cols)), key=lambda ij: (ij[0] + ij[1], ij[0]))[:n]
    ordered = sorted(cards, key=lambda c: (-degree.get(c["id"], 0), c["name"].lower()))
    lo, hi = -PAD, PAD
    plate = [iso(lo, lo), iso(cols + hi, lo), iso(cols + hi, rows + hi), iso(lo, rows + hi)]
    left, front, right = plate[3], plate[2], plate[1]
    parts = [f'<polygon class="slab-l" points="{_pts([left, front, (front[0], front[1] + SLAB), (left[0], left[1] + SLAB)])}"/>',
             f'<polygon class="slab-r" points="{_pts([front, right, (right[0], right[1] + SLAB), (front[0], front[1] + SLAB)])}"/>',
             f'<polygon class="plate" points="{_pts(plate)}"/>']
    for k in range(1, cols):
        parts.append(f'<path class="lane" d="M{_pts([iso(k, lo)])}L{_pts([iso(k, rows + hi)])}"/>')
    for k in range(1, rows):
        parts.append(f'<path class="lane" d="M{_pts([iso(lo, k)])}L{_pts([iso(cols + hi, k)])}"/>')
    reach = list(plate) + [(front[0], front[1] + SLAB)]
    labels = []
    for card, (i, j) in zip(ordered, cells):
        body, label, pts = _building(card, i, j, _floors(degree.get(card["id"], 0)))
        parts.append(body)
        labels.append(label)
        reach += pts
    if not n:
        x, y = iso(cols / 2, rows / 2)
        parts.append(f'<path class="sign" d="M{x:.1f},{y:.1f}v-26m-52,-18h104v18h-104z"/>')
        parts.append(f'<text class="lb sign-t" data-i18n="empty_lot" x="{x:.1f}" y="{y - 31:.1f}" text-anchor="middle">'
                     f'{html.escape(LABELS["en"]["empty_lot"])}</text>')
        reach += [(x - 56, y - 50), (x + 56, y)]
    xs, ys = [p[0] for p in reach], [p[1] for p in reach]
    x0, y0, w, h = min(xs) - 8, min(ys) - 8, max(xs) - min(xs) + 16, max(ys) - min(ys) + 16
    return (f'<svg class="iso" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" '
            f'role="group" aria-label="{html.escape(area, quote=True)}">{"".join(parts)}{"".join(labels)}</svg>')


def _card_view(pic: Picture, c: dict, degree: dict[str, int]) -> dict:
    """What the page needs to show one card."""
    links = [{"target": f[0], "how": " | ".join(f[1:]), "to": [t for t in pic.resolve(f[0]) if t != c["id"]]}
             for f in c["links"]]
    return {"id": c["id"], "name": c["name"], "short": short(c["name"]), "one_line": c["one_line"], "area": c["area"],
            "kind": c["kind"], "last_activity": c["last_activity"], "last_date": c.get("last_date"),
            "purpose": c["purpose"], "degree": degree.get(c["id"], 0),
            "exists": [" | ".join(f) for f in c["exists"]], "can_do": [" | ".join(f) for f in c["can_do"]],
            "needs": [{"need": f[0], "met": met(f[1]) if len(f) > 1 else "unknown", "by": by_what(f)}
                      for f in c["needs"]],
            "unfinished": [" | ".join(f) for f in c["unfinished"]], "ideas": [" | ".join(f) for f in c["ideas"]],
            "parts": [{"part": f[0], "why": " | ".join(f[1:])} for f in c["parts"]], "links": links,
            "themes": [f[0] for f in c["themes"]], "decisions": [" | ".join(f) for f in c["decisions"]],
            "unseen": [" | ".join(f) for f in c["unseen"]], "unknown": c["unknown"]}


def build(pic: Picture, today: date | None = None, title: str | None = None, lang: str = "en",
          quiet_days: int = 90) -> str:
    """The whole page as one string."""
    today = today or date.today()
    lang = lang if lang in LABELS else "en"
    degree = dict(pic.degree())
    areas = sorted(pic.by_area().items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))
    blocks = []
    for n, (area, cs) in enumerate(areas):
        items = "".join(
            f'<li><button type="button" class="pick" data-id="{c["id"]}"><bdi>{html.escape(c["name"])}</bdi></button></li>'
            for c in sorted(cs, key=lambda c: c["name"].lower()))
        size = "wide" if len(cs) > 4 else ""
        blocks.append(
            f'<section class="district {size}" style="--hue:{HUES[n % len(HUES)]}">'
            f'<h2><bdi>{html.escape(area)}</bdi> <span class="count">{len(cs)}</span></h2>'
            f'<div class="scene">{district_svg(area, cs, degree)}</div><ul class="names">{items}</ul></section>')
    data = {"lang": lang, "today": today.isoformat(), "quiet_days": quiet_days, "title": title or "",
            "newest": pic.newest(), "labels": LABELS,
            "cards": {cid: _card_view(pic, c, degree) for cid, c in pic.cards.items()},
            "areas": len(areas),
            "reports": {"brief": reports.brief(pic, today), "overlaps": reports.overlaps(pic),
                        "gaps": reports.gaps(pic, today, quiet_days), "reuse": reports.reuse(pic)}}
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")     # card text can never close the script
    page = resources.files(__package__).joinpath("town.html").read_text(encoding="utf-8")
    shown = html.escape(title or LABELS[lang]["title"])
    return theme.inject(page.replace("__LANG__", lang).replace("__DIR__", "rtl" if lang == "ar" else "ltr")
                        .replace("__TITLE__", shown).replace("<!--__DISTRICTS__-->", "".join(blocks))
                        .replace("/*__DATA__*/", blob))


def write(pic: Picture, path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build(pic, **kw), encoding="utf-8")
    return p
