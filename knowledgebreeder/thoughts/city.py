"""The city of thoughts: the map drawn as districts and buildings, in one HTML file that opens with no internet.

    district        a subject (your project cards are one, each book is one, inbox items join the subject they are about)
    infrastructure  a wide, low hall: a principle other ideas stand on
    resource        a store with a dome: a fact, a finding, a thing that exists
    utility         a tall tower with a mast: a method or a tool that can be used again
    need            an empty lot with a sign: something missing, waiting for a thought that helps it
    height          how many other thoughts it is joined to
    gold ring       a thought born from a marriage you approved

The drawing is plain SVG made here, like kb picture town. Every thought is also a button in a list under its
district, so the page works by keyboard and without the drawing. The page holds the person's own thoughts: it asks
the network for nothing, and a content security policy in the page forbids it.
"""

from __future__ import annotations

import html
import json
import math
from datetime import date
from importlib import resources
from pathlib import Path

from .. import theme
from ..picture.town import HUES, PAD, SLAB, TH, _pts, iso, short
from . import store as _store

FLOOR = 11
SHAPE = {"infrastructure": (0.40, 1, 3), "resource": (0.27, 1, 5), "utility": (0.15, 2, 8), "need": (0.36, 0, 0)}

LABELS = {
    "en": {
        "title": "The city of thoughts", "s_cards": "My projects", "s_married": "Married thoughts",
        "sub": "{n} thoughts in {s} subjects, {l} joins. {m} born from marriages.",
        "search": "Find a thought", "role_all": "Every kind",
        "infrastructure": "Infrastructure", "resource": "Resource", "utility": "Utility", "need": "Need",
        "legend_infrastructure": "Hall: infrastructure, a principle other ideas stand on",
        "legend_resource": "Dome: a resource, a fact or a thing that exists",
        "legend_utility": "Tower: a utility, a method or a tool to use again",
        "legend_need": "Empty lot: a need, waiting for a thought that helps it",
        "legend_ring": "Gold ring: born from a marriage you approved", "legend_h": "Taller: joined to more thoughts",
        "x_search": "Type a word: only the thoughts that hold it stay lit.",
        "x_role": "Show one kind of thought only.",
        "x_lang": "Switches the page between English and Arabic. Your thoughts keep their own words.",
        "x_pick": "Pick a building, or its name in the list, to read the thought, where it came from, and what it "
                  "is joined to. The thoughts it is joined to light up.",
        "x_copy": "Copy puts the command in your clipboard. Paste it in the terminal: kb records your yes or no. "
                  "The page itself saves nothing.",
        "pick": "Pick a building to read its thought.", "close": "Close", "from": "Where it came from",
        "quote": "In the source's words", "joins": "Joined to", "parents": "Born from", "children": "Its children",
        "check": "Check: {f} is in none of the lines it came from.", "by_words": "word match",
        "j_needs_out": "needs", "j_needs_in": "is needed by", "j_causes_out": "causes", "j_causes_in": "is caused by",
        "j_is part of_out": "is part of", "j_is part of_in": "holds",
        "j_contradicts_out": "contradicts", "j_contradicts_in": "contradicts",
        "j_may help_out": "may help", "j_may help_in": "may be helped by",
        "marriages": "Marriages waiting for your yes", "m_note": "A model proposed each new thought from two of "
        "yours. It joins the city only when you approve it.", "approve": "Approve", "decline": "Decline",
        "copy": "Copy", "copied": "Copied", "parent": "Parent", "child": "New thought", "why": "Why",
        "gaps": "Gaps", "g_waits_model": "Inbox items waiting for a model to read them (kb thoughts read)",
        "g_waits_reader": "Screenshots and voice notes waiting for a reader on this laptop",
        "g_waits_frame": "Books on the shelf, not yet framed (kb books frame)",
        "g_contradictions": "Thoughts that contradict each other: which one holds?",
        "g_needs_alone": "Needs nothing on the map helps yet", "g_alone": "Thoughts joined to nothing",
        "g_thin": "Subjects with only one source", "none": "Nothing here.",
        "note": "Joins marked word match were found by matching words: a hint to look, not a finding.",
        "private": "This file holds your thoughts. It makes no network requests.",
        "made": "Made {d} with kb thoughts city.",
    },
    "ar": {
        "title": "مدينة الأفكار", "s_cards": "مشاريعي", "s_married": "أفكار متزوجة",
        "sub": "{n} فكرة في {s} موضوعات، و{l} رابط. {m} وُلدت من زواج أفكار.",
        "search": "ابحث عن فكرة", "role_all": "كل الأنواع",
        "infrastructure": "بنية تحتية", "resource": "مورد", "utility": "مرفق", "need": "حاجة",
        "legend_infrastructure": "قاعة: بنية تحتية، مبدأ تقوم عليه أفكار أخرى",
        "legend_resource": "قبة: مورد، حقيقة أو شيء موجود",
        "legend_utility": "برج: مرفق، طريقة أو أداة تُستعمل مرة بعد مرة",
        "legend_need": "أرض فاضية: حاجة تنتظر فكرة تساعدها",
        "legend_ring": "حلقة ذهبية: وُلدت من زواج وافقت عليه", "legend_h": "الأعلى: مرتبط بأفكار أكثر",
        "x_search": "اكتب كلمة: تبقى مضيئة الأفكار التي فيها فقط.",
        "x_role": "اعرض نوعاً واحداً من الأفكار فقط.",
        "x_lang": "يبدّل الصفحة بين العربية والإنجليزية. أفكارك تبقى بكلماتها.",
        "x_pick": "اختر مبنى، أو اسمه في القائمة، لتقرأ الفكرة ومن أين جاءت وبماذا ترتبط. تضيء الأفكار المرتبطة بها.",
        "x_copy": "زر النسخ يضع الأمر في الحافظة. الصقه في الطرفية فيسجّل kb موافقتك أو رفضك. الصفحة نفسها لا تحفظ شيئاً.",
        "pick": "اختر مبنى لتقرأ فكرته.", "close": "إغلاق", "from": "من أين جاءت",
        "quote": "بكلمات المصدر", "joins": "مرتبطة بـ", "parents": "وُلدت من", "children": "أفكار وُلدت منها",
        "check": "راجع: {f} غير موجود في السطور التي جاءت منها.", "by_words": "مطابقة كلمات",
        "j_needs_out": "تحتاج", "j_needs_in": "تحتاجها", "j_causes_out": "تسبب", "j_causes_in": "سببها",
        "j_is part of_out": "جزء من", "j_is part of_in": "تضم",
        "j_contradicts_out": "تناقض", "j_contradicts_in": "تناقض",
        "j_may help_out": "قد تساعد", "j_may help_in": "قد تساعدها",
        "marriages": "زيجات تنتظر موافقتك",
        "m_note": "اقترح نموذج كل فكرة جديدة من فكرتين عندك. لا تدخل المدينة إلا بموافقتك.",
        "approve": "موافقة", "decline": "رفض", "copy": "نسخ", "copied": "نُسخ", "parent": "الأصل",
        "child": "الفكرة الجديدة", "why": "السبب",
        "gaps": "الفجوات", "g_waits_model": "عناصر في الوارد تنتظر نموذجاً يقرأها (kb thoughts read)",
        "g_waits_reader": "صور شاشة ورسائل صوتية تنتظر قارئاً على هذا الجهاز",
        "g_waits_frame": "كتب على الرف لم تُؤطَّر بعد (kb books frame)",
        "g_contradictions": "أفكار تناقض بعضها: أيها يصح؟",
        "g_needs_alone": "حاجات لا يساعدها شيء في الخريطة بعد", "g_alone": "أفكار غير مرتبطة بشيء",
        "g_thin": "موضوعات لها مصدر واحد فقط", "none": "لا شيء هنا.",
        "note": "الروابط المعلّمة بمطابقة كلمات وُجدت بمطابقة الكلمات: إشارة للنظر وليست نتيجة.",
        "private": "هذا الملف يحمل أفكارك ولا يتصل بأي شبكة.",
        "made": "صُنع في {d} بـ kb thoughts city.",
    },
}


def _box(cx: float, cy: float, s: float, h: float) -> list[str]:
    a, b, c, d = (cx - s, cy + s), (cx + s, cy + s), (cx + s, cy - s), (cx - s, cy - s)
    return [f'<polygon class="wl" points="{_pts([iso(*a), iso(*b), iso(*b, h), iso(*a, h)])}"/>',
            f'<polygon class="wr" points="{_pts([iso(*b), iso(*c), iso(*c, h), iso(*b, h)])}"/>',
            f'<polygon class="rf" points="{_pts([iso(*a, h), iso(*b, h), iso(*c, h), iso(*d, h)])}"/>']


def floors(role: str, degree: int) -> int:
    s, lo, hi = SHAPE.get(role, SHAPE["resource"])
    return 0 if role == "need" else min(lo + degree, hi)


def building(t: dict, i: int, j: int, degree: int, label: bool) -> tuple[str, str, list[tuple[float, float]]]:
    """One thought as SVG, its label, and the points it reaches."""
    role = t["role"] if t["role"] in SHAPE else "resource"
    s = SHAPE[role][0]
    cx, cy = i + 0.5, j + 0.5
    h = floors(role, degree) * FLOOR
    g: list[str] = []
    if role == "need":
        lot = [iso(cx - s, cy + s), iso(cx + s, cy + s), iso(cx + s, cy - s), iso(cx - s, cy - s)]
        x, y = iso(cx, cy)
        g += [f'<polygon class="lot" points="{_pts(lot)}"/>',
              f'<path class="post" d="M{x:.1f},{y:.1f}v-20"/>',
              f'<rect class="board" x="{x - 11:.1f}" y="{y - 30:.1f}" width="22" height="11" rx="2"/>']
        top = y - 30
    else:
        g += _box(cx, cy, s, h)
        if role == "resource":
            x, y = iso(cx, cy, h)
            g.append(f'<ellipse class="dome" cx="{x:.1f}" cy="{y:.1f}" rx="{s * 52:.1f}" ry="{s * 26:.1f}"/>')
            g.append(f'<path class="dome" d="M{x - s * 40:.1f},{y:.1f}a{s * 40:.1f},{s * 40:.1f} 0 0 1 {s * 80:.1f},0z"/>')
            top = y - s * 40
        elif role == "utility":
            x, y = iso(cx, cy, h)
            g.append(f'<path class="mast" d="M{x:.1f},{y:.1f}v-14m-5,5h10"/>')
            top = y - 14
        else:
            for k in range(3):                       # the hall's columns on its front faces
                u = 0.22 + 0.28 * k
                p0 = (cx - s + 2 * s * u, cy + s)
                g.append(f'<path class="col" d="M{_pts([iso(*p0, 2)])}L{_pts([iso(*p0, max(h - 3, 4))])}"/>')
            top = iso(cx, cy, h)[1] - TH * s
    if t.get("parents"):
        x, y = iso(cx, cy, h)
        g.append(f'<circle class="ring" cx="{x:.1f}" cy="{(top if role != "infrastructure" else y) - 8:.1f}" r="5"/>')
        top -= 14
    lx, ly = iso(cx, cy, h)[0], top - 6
    text = html.escape(t["text"], quote=True)
    body = (f'<g class="b r-{role}" id="b-{t["id"]}" data-id="{t["id"]}" tabindex="0" role="button" '
            f'aria-label="{text}"><title>{text}</title>{"".join(g)}</g>')
    lab = (f'<text class="lb" data-for="{t["id"]}" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle">'
           f'{html.escape(short(t["text"], 20))}</text>') if label else ""
    x0, y0 = iso(cx - s, cy + s)
    x1, _ = iso(cx + s, cy - s)
    reach = [iso(cx - s, cy + s), iso(cx + s, cy - s), iso(cx + s, cy + s), (lx - 64, ly - 12), (lx + 64, ly),
             (x0, y0), (x1, top - 4)]
    return body, lab, reach


def district_svg(subject: str, ts: list[dict], degree: dict[str, int]) -> str:
    n = len(ts)
    rows = 1 if n <= 3 else 2 if n <= 10 else 3 if n <= 18 else math.ceil(math.sqrt(n / 2))
    cols = max(1, math.ceil(n / rows))
    cells = sorted(((i, j) for j in range(rows) for i in range(cols)), key=lambda ij: (ij[0] + ij[1], ij[0]))[:n]
    ordered = sorted(ts, key=lambda t: (-degree.get(t["id"], 0), t["text"].lower()))
    plate = [iso(-PAD, -PAD), iso(cols + PAD, -PAD), iso(cols + PAD, rows + PAD), iso(-PAD, rows + PAD)]
    left, front, right = plate[3], plate[2], plate[1]
    parts = [f'<polygon class="slab-l" points="{_pts([left, front, (front[0], front[1] + SLAB), (left[0], left[1] + SLAB)])}"/>',
             f'<polygon class="slab-r" points="{_pts([front, right, (right[0], right[1] + SLAB), (front[0], front[1] + SLAB)])}"/>',
             f'<polygon class="plate" points="{_pts(plate)}"/>']
    for k in range(1, cols):
        parts.append(f'<path class="lane" d="M{_pts([iso(k, -PAD)])}L{_pts([iso(k, rows + PAD)])}"/>')
    for k in range(1, rows):
        parts.append(f'<path class="lane" d="M{_pts([iso(-PAD, k)])}L{_pts([iso(cols + PAD, k)])}"/>')
    reach = list(plate) + [(front[0], front[1] + SLAB)]
    labels = []
    few = n <= 8
    for t, (i, j) in zip(ordered, cells):
        body, lab, pts = building(t, i, j, degree.get(t["id"], 0), few or degree.get(t["id"], 0) >= 3)
        parts.append(body)
        labels.append(lab)
        reach += pts
    xs, ys = [p[0] for p in reach], [p[1] for p in reach]
    x0, y0, w, h = min(xs) - 8, min(ys) - 8, max(xs) - min(xs) + 16, max(ys) - min(ys) + 16
    return (f'<svg class="iso" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" '
            f'role="group" aria-label="{html.escape(subject, quote=True)}">{"".join(parts)}{"".join(labels)}</svg>')


def _named(subject: str) -> str:
    """kb's own district names say themselves in the page's language; your subjects keep their own words."""
    key = {_store.CARDS_SUBJECT: "s_cards", _store.MARRIED_SUBJECT: "s_married"}.get(subject)
    return f' data-i18n="{key}"' if key else ""


def _view(m: _store.Map, t: dict) -> dict:
    s = m.sources.get(t["source"]) or {}
    return {"id": t["id"], "text": t["text"], "role": t["role"], "subject": t["subject"], "from": t.get("from", ""),
            "quote": t.get("quote", ""), "source": s.get("title") or t["source"], "kind": s.get("kind", ""),
            "ref": s.get("ref", ""), "parents": t.get("parents", []), "check": t.get("check", []), "by": t.get("by")}


def build(m: _store.Map, today: date | None = None, lang: str = "en", title: str | None = None) -> str:
    today = today or date.today()
    lang = lang if lang in LABELS else "en"
    live, degree = m.live(), dict(m.degree())
    by: dict[str, list[dict]] = {}
    for t in live.values():
        by.setdefault(t["subject"], []).append(t)
    order = sorted(by.items(), key=lambda kv: (kv[0] != _store.CARDS_SUBJECT, -len(kv[1]), kv[0].lower()))
    blocks = []
    for n, (subject, ts) in enumerate(order):
        items = "".join(f'<li><button type="button" class="pick r-{t["role"]}" data-id="{t["id"]}">'
                        f'<bdi>{html.escape(short(t["text"], 48))}</bdi></button></li>'
                        for t in sorted(ts, key=lambda t: (-degree.get(t["id"], 0), t["text"].lower())))
        wide = " wide" if len(ts) > 6 else ""
        blocks.append(f'<section class="district{wide}" style="--hue:{HUES[n % len(HUES)]}">'
                      f'<h2><bdi{_named(subject)}>{html.escape(subject)}</bdi> <span class="count">{len(ts)}</span></h2>'
                      f'<div class="scene">{district_svg(subject, ts, degree)}</div><ul class="names">{items}</ul></section>')
    g = _store.gaps(m)
    view = lambda t: {"id": t["id"], "text": t["text"], "subject": t["subject"]}
    data = {"lang": lang, "today": today.isoformat(), "title": title or "", "labels": LABELS,
            "thoughts": {k: _view(m, t) for k, t in live.items()},
            "links": [{"a": ln["a"], "b": ln["b"], "kind": ln["kind"], "why": ln.get("why", ""),
                       "words": ln["kind"] == _store.HINT} for ln in m.links if ln["a"] in live and ln["b"] in live],
            "subjects": len(by), "special": {_store.CARDS_SUBJECT: "s_cards", _store.MARRIED_SUBJECT: "s_married"},
            "marriages": [{"id": r["id"], "child": r["child"], "why": r.get("why", ""), "role": r["role"],
                           "notes": r.get("notes", []), "a": view(m.thoughts[r["a"]]), "b": view(m.thoughts[r["b"]])}
                          for r in g["marriages"] if r["a"] in m.thoughts and r["b"] in m.thoughts],
            "gaps": {"waits_model": [s.get("title") or s["id"] for s in g["waits_model"]],
                     "waits_reader": [s.get("title") or s["id"] for s in g["waits_reader"]],
                     "waits_frame": [s.get("title") or s["id"] for s in g["waits_frame"]],
                     "contradictions": [{"a": view(live[ln["a"]]), "b": view(live[ln["b"]])}
                                        for ln in g["contradictions"]],
                     "needs_alone": [view(t) for t in g["needs_alone"]],
                     "alone": [view(t) for t in g["alone"]][:40], "thin": g["thin"]}}
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    page = resources.files(__package__).joinpath("city.html").read_text(encoding="utf-8")
    return theme.inject(page.replace("__LANG__", lang).replace("__DIR__", "rtl" if lang == "ar" else "ltr")
                        .replace("__TITLE__", html.escape(title or LABELS[lang]["title"]))
                        .replace("<!--__DISTRICTS__-->", "".join(blocks)).replace("/*__DATA__*/", blob))


def write(m: _store.Map, path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build(m, **kw), encoding="utf-8")
    return p
