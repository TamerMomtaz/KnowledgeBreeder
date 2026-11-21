"""One advice run on one page: every model's answer in one list, in one HTML file that opens with no internet.

    kb picture page             your newest advice run
    kb picture page RUN         that run

Each model's answer stays whole. Every piece shows who wrote it and its own number, so a rating still credits
the right model. Pieces from different models that rest on the same lines of your cards are put together:
the same advice twice is a stronger sign, and two different answers on the same lines are worth reading side
by side. The match is made from the lines each piece cites and the words it uses, not from what it means, and
the page says so.

You tick what you would act on, and the page writes the exact kb commands to paste. The page itself saves
nothing: kb stays the only thing that writes to the run log, and you stay the one who runs it.

The file holds lines from your own cards. It asks the browser for nothing from the network, and a content
security policy in the page forbids it.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from importlib import resources
from pathlib import Path

from ..runlog import RunLog, query

HUES = (208, 152, 28, 276, 332, 96, 46, 184)
_WORD = re.compile(r"\w+")
_STOP = frozenset("""
    about after also been being both could does each from have into just make made many more most much must only
    other over same should some such than that their them then there these they this those very what when where
    which while will with within without would your yours project projects
""".split())
_RATED = re.compile(r"would act on (none|[\d, ]+) of (\d+)")
KINDS = ("do", "stop", "join", "decide", "ask")

LABELS = {
    "en": {
        "title": "Advice, side by side", "lang_name": "English",
        "sub": "Run {run}, {date}. {n} pieces from {m}.",
        "sign": "Models wrote this. Check each piece against the lines it cites before you act on it. You sign.",
        "order": "Pieces that rest on the same lines come first, then each model's list in its own order.",
        "same": "More than one model, on the same lines",
        "same_note": "Put together because they cite the same lines of your cards and use some of the same words. "
                     "That is a match of words, not of meaning. If they say the same thing, it counts twice. "
                     "If they differ, read both.",
        "act": "I would act on this", "why": "Why", "first_step": "First step", "from": "From",
        "lines": "The lines it cites", "check": "Check: {f} is in none of the lines it cites.",
        "kind_do": "do", "kind_stop": "stop", "kind_join": "join", "kind_decide": "decide", "kind_ask": "ask",
        "who_h": "Who answered", "read": "read {n} lines", "left_out": "{n} more did not fit",
        "shown": "{n} pieces shown", "dropped": "{n} cited no line kb sent, so they are not shown",
        "failed": "gave nothing: {e}", "note": "Note: {w}",
        "here": "on this machine", "network": "on your network", "outside": "outside this machine",
        "lessons_h": "Lessons this run followed", "no_lessons": "This run followed no lessons.",
        "record_h": "Record what you think",
        "record_note": "Tick the pieces you would act on. The commands fill in by themselves. Paste each one in "
                       "your terminal, in the KnowledgeBreeder folder.",
        "none_from": "None of these", "why_ph": "Why, in a few words (optional)",
        "ticked": "{k} of {n} ticked", "empty": "Nothing ticked yet.",
        "pick_h": "Which answer is better overall?", "pick_note": "This is a separate vote from the ticks.",
        "rated": "Recorded: you would act on {list} of {n} ({p}%).", "picked_done": "Recorded: you picked {w}.",
        "copy": "Copy", "copied": "Copied",
        "history_h": "Who earns your ticks, run by run",
        "history_note": "The share of each model's pieces you said you would act on. If the loop works, it rises.",
        "history_few": "Rate a few more runs and the trend shows here.", "picked": "picked",
        "date": "Date", "run": "Run", "mean": "So far", "runs": "{n} rated",
        "private": "This file holds lines from your own cards. It makes no network requests. Keep it on this machine.",
        "made": "Made {d} with kb picture page.", "none": "none",
    },
    "ar": {
        "title": "النصائح جنباً إلى جنب", "lang_name": "العربية",
        "sub": "التشغيل {run}، {date}. عدد النصائح: {n}، من {m}.",
        "sign": "كتبت النماذج هذه النصائح. راجع كل نصيحة مقابل الأسطر التي تستند إليها قبل أن تعمل بها. القرار لك.",
        "order": "النصائح التي تستند إلى نفس الأسطر تأتي أولاً، ثم قائمة كل نموذج بترتيبها.",
        "same": "أكثر من نموذج، على نفس الأسطر",
        "same_note": "جُمعت لأنها تستند إلى نفس الأسطر من بطاقاتك وتستخدم بعض الكلمات نفسها. "
                     "هذا تطابق في الكلمات وليس في المعنى. إن قالت الشيء نفسه فهو صوتان. "
                     "وإن اختلفت فاقرأ الاثنتين.",
        "act": "سأعمل بهذه", "why": "لماذا", "first_step": "الخطوة الأولى", "from": "المصدر",
        "lines": "الأسطر التي تستند إليها", "check": "تحقق: {f} غير موجود في أي من الأسطر التي تستند إليها.",
        "kind_do": "افعل", "kind_stop": "توقف", "kind_join": "اربط", "kind_decide": "قرر", "kind_ask": "اسأل",
        "who_h": "من أجاب", "read": "الأسطر المقروءة: {n}", "left_out": "لم يتسع: {n}",
        "shown": "النصائح المعروضة: {n}", "dropped": "لم تستند إلى أي سطر أرسله kb فلم تُعرض: {n}",
        "failed": "لم يقدم شيئاً: {e}", "note": "ملاحظة: {w}",
        "here": "على هذا الجهاز", "network": "على شبكتك", "outside": "خارج هذا الجهاز",
        "lessons_h": "الدروس التي اتبعها هذا التشغيل", "no_lessons": "لم يتبع هذا التشغيل أي درس.",
        "record_h": "سجّل رأيك",
        "record_note": "ضع علامة على النصائح التي ستعمل بها. تُكتب الأوامر وحدها. الصق كل أمر في الطرفية، "
                       "داخل مجلد KnowledgeBreeder.",
        "none_from": "لا شيء من هذه", "why_ph": "لماذا، في كلمات قليلة (اختياري)",
        "ticked": "محدد: {k} من {n}", "empty": "لم تحدد شيئاً بعد.",
        "pick_h": "أي إجابة أفضل إجمالاً؟", "pick_note": "هذا تصويت منفصل عن العلامات.",
        "rated": "سُجّل: ستعمل بـ {list} من {n} ({p}٪).", "picked_done": "سُجّل: اخترت {w}.",
        "copy": "نسخ", "copied": "تم النسخ",
        "history_h": "من يكسب علاماتك، تشغيلاً بعد تشغيل",
        "history_note": "نسبة نصائح كل نموذج التي قلت إنك ستعمل بها. إن نجحت الحلقة فهي ترتفع.",
        "history_few": "قيّم بضع تشغيلات أخرى وسيظهر الاتجاه هنا.", "picked": "مختار",
        "date": "التاريخ", "run": "التشغيل", "mean": "حتى الآن", "runs": "مقيّمة: {n}",
        "private": "يحمل هذا الملف أسطراً من بطاقاتك. لا يطلب شيئاً من الشبكة. أبقه على هذا الجهاز.",
        "made": "صُنع {d} بأمر kb picture page.", "none": "لا شيء",
    },
}

_WHERE = {"this machine": "here", "your network": "network", "outside": "outside"}


def _words(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(text.lower()) if len(w) > 3 and w not in _STOP and not w.isdigit())


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def likeness(p: dict, q: dict) -> float | None:
    """How alike two pieces from different models look, or None when they do not look like the same idea.
    Shared lines count most: the evidence is the same for every model, so citing the same lines means
    looking at the same thing."""
    lines, words = _jaccard(p["_lines"], q["_lines"]), _jaccard(p["_words"], q["_words"])
    if lines >= 0.5 or (lines > 0 and words >= 0.12) or words >= 0.35:
        return lines + words
    return None


def _rated(note: str | None) -> list[int] | None:
    m = _RATED.search(note or "")
    if not m:
        return None
    return [] if m.group(1) == "none" else [int(x) for x in re.findall(r"\d+", m.group(1))]


def gather(log: RunLog, run_id: str) -> dict:
    """Everything the page shows about one advice run."""
    shown = query.show(log, run_id, payloads=True)
    if shown["task"] != "advise":
        raise KeyError(f"{shown['id']} is a {shown['task']} run, not advice.")
    notes = {(r["step_id"], r["name"]): r["note"] for r in log.db.execute(
        "SELECT step_id, name, note FROM scores WHERE run_id = ? AND step_id IS NOT NULL", (shown["id"],))}
    answers, lessons = [], []
    for s in shown["steps"]:
        if s["name"] != "advise" or not s["worker"]:
            continue
        a = {"worker": s["worker"], "model": s["version"] or "", "step": s["id"], "ms": s["duration_ms"],
             "cost": s["cost"], "where": _WHERE.get((s.get("meta") or {}).get("where") or "", "")}
        if s["status"] != "ok":
            answers.append({**a, "error": (s["error"] or "no answer").splitlines()[0], "pieces": []})
            continue
        inp = s["input"] if isinstance(s["input"], dict) else {}
        out = s["output"] if isinstance(s["output"], dict) else {}
        ev = {e["id"]: e for e in inp.get("evidence", []) if isinstance(e, dict) and "id" in e}
        lessons = lessons or list(inp.get("lessons") or [])
        pieces = []
        for n, p in enumerate(out.get("advice") or [], 1):
            lines = [ev[c] for c in p.get("cites", []) if c in ev]
            pieces.append({**p, "n": n, "worker": s["worker"], "lines": lines,
                           "_lines": frozenset(" ".join(ln["text"].split()) for ln in lines),
                           "_words": _words(" ".join(str(p.get(k) or "") for k in ("move", "why", "first_step")))})
        rated = _rated(notes.get((s["id"], "would_act"))) if "would_act" in s["scores"] else None
        answers.append({**a, "pieces": pieces, "dropped": len(out.get("dropped") or []),
                        "warnings": list(out.get("warnings") or []), "lines_sent": len(ev),
                        "left_out": inp.get("left_out") or 0, "rated": rated,
                        "would_act": s["scores"].get("would_act"), "picked": s["scores"].get("picked")})
    return {"run": shown["id"], "date": (shown["started"] or "")[:10], "subject": shown["subject"] or "",
            "answers": answers, "lessons": lessons}


def group(answers: list[dict]) -> list[list[dict]]:
    """One list from every answer. Pieces from different models that look alike are joined, never two from the
    same model, most alike first. Groups of several models come first, then by how early their pieces came."""
    order = {a["worker"]: i for i, a in enumerate(answers)}
    pieces = [p for a in answers for p in a["pieces"]]
    home = {id(p): [p] for p in pieces}
    pairs = []
    for i, p in enumerate(pieces):
        for q in pieces[i + 1:]:
            if p["worker"] != q["worker"] and (score := likeness(p, q)) is not None:
                pairs.append((-score, order[p["worker"]], p["n"], q["n"], p, q))
    for *_, p, q in sorted(pairs, key=lambda t: t[:4]):
        gp, gq = home[id(p)], home[id(q)]
        if gp is gq or {x["worker"] for x in gp} & {x["worker"] for x in gq}:
            continue
        gp.extend(gq)
        for x in gq:
            home[id(x)] = gp
    groups = list({id(g): g for g in home.values()}.values())
    for g in groups:
        g.sort(key=lambda p: order[p["worker"]])
    return sorted(groups, key=lambda g: (-len(g), min(p["n"] for p in g), order[g[0]["worker"]]))


def history(log: RunLog, limit: int = 12) -> list[dict]:
    """The advice runs you have rated or picked from, oldest first: who you would act on, and whom you picked."""
    rows = log.db.execute("""
        SELECT r.id AS run, r.started, s.worker, c.name, c.value FROM scores c
        JOIN steps s ON s.id = c.step_id JOIN runs r ON r.id = c.run_id
        WHERE r.task = 'advise' AND c.name IN ('would_act', 'picked') ORDER BY r.started, c.id""").fetchall()
    runs: dict[str, dict] = {}
    for r in rows:
        x = runs.setdefault(r["run"], {"run": r["run"], "date": r["started"][:10], "workers": {}})
        x["workers"].setdefault(r["worker"], {})[r["name"]] = r["value"]
    return list(runs.values())[-limit:]


def _t(lang: str, key: str, **v) -> str:
    """A label in the page's language. In Arabic each filled-in value is isolated, so a run id, a date or a list
    of names keeps its own order inside the sentence."""
    s = LABELS[lang].get(key) or LABELS["en"][key]
    for k, x in v.items():
        s = s.replace("{" + k + "}", f"\u2068{x}\u2069" if lang == "ar" else str(x))
    return s


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _tag(worker: str, hue: int, model: str = "") -> str:
    title = f' title="{_e(model)}"' if model else ""
    return f'<span class="tag" style="--hue:{hue}"{title}><bdi>{_e(worker)}</bdi></span>'


def _piece(p: dict, lang: str, hue: int, locked: list[int] | None) -> str:
    kind = p.get("kind") if p.get("kind") in KINDS else "do"
    tick = "checked " if locked and p["n"] in locked else ""
    off = "disabled " if locked is not None else ""
    L = [f'<article class="piece" style="--hue:{hue}" data-worker="{_e(p["worker"])}" data-n="{p["n"]}">',
         (f'<div class="who">{_tag(p["worker"], hue)}<span class="num">#{p["n"]}</span>'
          f'<span class="kind">{_e(_t(lang, "kind_" + kind))}</span></div>'),
         f'<p class="move" dir="auto">{_e(p.get("move", ""))}</p>']
    if p.get("why"):
        L.append(f'<p class="why"><b>{_e(_t(lang, "why"))}:</b> <span dir="auto">{_e(p["why"])}</span></p>')
    if p.get("first_step"):
        L.append(f'<p class="step"><b>{_e(_t(lang, "first_step"))}:</b> <span dir="auto">{_e(p["first_step"])}</span></p>')
    if p.get("source"):
        srcs = "; ".join(f'<bdi class="s">{_e(s)}</bdi>' for s in p["source"])
        L.append(f'<p class="src"><b>{_e(_t(lang, "from"))}:</b> {srcs}</p>')
    if p["lines"]:
        items = "".join(f'<li><span class="eid">{_e(ln["id"])}</span> <span dir="auto">{_e(ln["text"])}</span></li>'
                        for ln in p["lines"])
        L.append(f'<details><summary>{_e(_t(lang, "lines"))} ({len(p["lines"])})</summary><ol class="lines">{items}</ol></details>')
    if p.get("figures_not_in_source"):
        L.append(f'<p class="check">{_e(_t(lang, "check", f=", ".join(p["figures_not_in_source"])))}</p>')
    L.append(f'<label class="tick"><input type="checkbox" {tick}{off}data-worker="{_e(p["worker"])}" '
             f'data-n="{p["n"]}"> <span>{_e(_t(lang, "act"))}</span></label></article>')
    return "".join(L)


def _who(a: dict, lang: str, hue: int) -> str:
    bits = [f"<bdi>{_e(a['model'])}</bdi>"] if a["model"] else []
    if a["where"]:
        bits.append(_e(_t(lang, a["where"])))
    if "error" in a:
        bits.append(_e(_t(lang, "failed", e=a["error"])))
    else:
        bits.append(_e(_t(lang, "read", n=a["lines_sent"])) + (", " + _e(_t(lang, "left_out", n=a["left_out"]))
                                                               if a["left_out"] else ""))
        bits.append(_e(_t(lang, "shown", n=len(a["pieces"]))))
        if a["dropped"]:
            bits.append(_e(_t(lang, "dropped", n=a["dropped"])))
    if a["ms"]:
        bits.append(f"<bdi>{a['ms'] / 1000:.1f} s</bdi>")
    if a["cost"]:
        bits.append(f"<bdi>${a['cost']:.4f}</bdi>")
    notes = "".join(f'<p class="warn">{_e(_t(lang, "note", w=w))}</p>' for w in a.get("warnings", []))
    return f'<li>{_tag(a["worker"], hue, a["model"])} <span class="meta">{" · ".join(bits)}</span>{notes}</li>'


def _history(rows: list[dict], workers: list[str], hues: dict[str, int], lang: str) -> str:
    if not rows:
        return f'<p class="soft">{_e(_t(lang, "history_few"))}</p>'
    names = list(dict.fromkeys(workers + [w for r in rows for w in r["workers"]]))
    head = "".join(f"<th>{_tag(w, hues.get(w, 0))}</th>" for w in names)
    body = []
    for r in reversed(rows):
        cells = []
        for w in names:
            s = r["workers"].get(w, {})
            v = s.get("would_act")
            bar = (f'<span class="bar" style="--v:{v:.3f};--hue:{hues.get(w, 0)}"></span><bdi>{round(100 * v)}%</bdi>'
                   if v is not None else '<span class="soft">·</span>')
            star = f' <span class="star" title="{_e(_t(lang, "picked"))}">★</span>' if s.get("picked") == 1.0 else ""
            cells.append(f"<td>{bar}{star}</td>")
        body.append(f'<tr><td><bdi>{_e(r["date"])}</bdi></td><td class="rid"><bdi>{_e(r["run"])}</bdi></td>'
                    f'{"".join(cells)}</tr>')
    means = []
    for w in names:
        vals = [r["workers"][w]["would_act"] for r in rows if "would_act" in r["workers"].get(w, {})]
        wins = sum(r["workers"].get(w, {}).get("picked") == 1.0 for r in rows)
        means.append(f'<td>{f"<bdi>{round(100 * sum(vals) / len(vals))}%</bdi> " if vals else ""}'
                     f'<span class="soft">{_e(_t(lang, "runs", n=len(vals)))}'
                     f'{f", ★ {wins}" if wins else ""}</span></td>')
    few = f'<p class="soft">{_e(_t(lang, "history_few"))}</p>' if len(rows) < 3 else ""
    return (f'<div class="scroll"><table class="hist"><thead><tr><th>{_e(_t(lang, "date"))}</th><th class="rid">{_e(_t(lang, "run"))}</th>'
            f'{head}</tr></thead><tbody>{"".join(body)}</tbody><tfoot><tr><td>{_e(_t(lang, "mean"))}</td><td class="rid"></td>'
            f'{"".join(means)}</tr></tfoot></table></div>{few}')


def build(data: dict, hist: list[dict] | None = None, lang: str = "en", log_flag: str | None = None,
          today: date | None = None) -> str:
    """The whole page as one string. ``log_flag`` is the run log's path when the commands must name it."""
    lang = lang if lang in LABELS else "en"
    today = today or date.today()
    answers = data["answers"]
    workers = [a["worker"] for a in answers]
    hues = {w: HUES[i % len(HUES)] for i, w in enumerate(workers)}
    locked = {a["worker"]: a["rated"] if a["would_act"] is not None else None for a in answers}
    for a in answers:
        if a["would_act"] is not None and locked[a["worker"]] is None:
            locked[a["worker"]] = []                # rated before notes were kept: lock it, tick nothing
    groups = group(answers)
    parts = []
    for g in groups:
        inner = "".join(_piece(p, lang, hues[p["worker"]], locked[p["worker"]]) for p in g)
        if len(g) > 1:
            parts.append(f'<section class="group"><h3>{_e(_t(lang, "same"))} '
                         f'{"".join(_tag(p["worker"], hues[p["worker"]]) for p in g)}</h3>'
                         f'<p class="soft small">{_e(_t(lang, "same_note"))}</p>{inner}</section>')
        else:
            parts.append(inner)
    n_pieces = sum(len(a["pieces"]) for a in answers)
    lessons = ('<ol class="lessons">' + "".join(f'<li dir="auto">{_e(x)}</li>' for x in data["lessons"]) + "</ol>"
               if data["lessons"] else f'<p class="soft">{_e(_t(lang, "no_lessons"))}</p>')
    rate = []
    for a in answers:
        if "error" in a or not a["pieces"]:
            continue
        hue = hues[a["worker"]]
        if a["would_act"] is not None:
            got = locked[a["worker"]] or []
            rate.append(f'<div class="rate done">{_tag(a["worker"], hue)} '
                        f'{_e(_t(lang, "rated", list=", ".join(map(str, got)) or _t(lang, "none"), n=len(a["pieces"]), p=round(100 * a["would_act"])))}</div>')
            continue
        rate.append(f'<div class="rate" data-worker="{_e(a["worker"])}" data-total="{len(a["pieces"])}">'
                    f'<div class="row">{_tag(a["worker"], hue, a["model"])} <span class="count"></span></div>'
                    f'<label class="none"><input type="checkbox" class="none-box"> {_e(_t(lang, "none_from"))}</label>'
                    f'<input type="text" class="reason" placeholder="{_e(_t(lang, "why_ph"))}" aria-label="{_e(_t(lang, "why_ph"))}" dir="auto">'
                    f'<div class="cmd" hidden><code dir="ltr"></code><button type="button" class="copy">{_e(_t(lang, "copy"))}</button></div></div>')
    pick = ""
    ok = [a for a in answers if "error" not in a and a["pieces"]]
    if len(ok) > 1:
        done = next((a["worker"] for a in answers if a["picked"] == 1.0), None)
        if done or any(a["picked"] is not None for a in answers):
            pick = f'<div class="pick done">{_e(_t(lang, "picked_done", w=done or "?"))}</div>'
        else:
            radios = "".join(f'<label class="radio"><input type="radio" name="pick" value="{_e(a["worker"])}"> '
                             f'{_tag(a["worker"], hues[a["worker"]], a["model"])}</label>' for a in ok)
            pick = (f'<div class="pick"><h3>{_e(_t(lang, "pick_h"))}</h3><p class="soft small">{_e(_t(lang, "pick_note"))}</p>'
                    f'<div class="radios">{radios}</div><div class="cmd" hidden><code dir="ltr"></code>'
                    f'<button type="button" class="copy">{_e(_t(lang, "copy"))}</button></div></div>')
    blob = json.dumps({"run": data["run"], "multi": len(ok) > 1, "log": log_flag, "labels": LABELS[lang]},
                      ensure_ascii=False).replace("<", "\\u003c")
    page = resources.files(__package__).joinpath("page.html").read_text(encoding="utf-8")
    fill = {
        "__LANG__": lang, "__DIR__": "rtl" if lang == "ar" else "ltr", "__TITLE__": _e(_t(lang, "title")),
        "__SUB__": _e(_t(lang, "sub", run=data["run"], date=data["date"], n=n_pieces,
                         m=", ".join(workers) or "-")),
        "__SIGN__": _e(_t(lang, "sign")), "__ORDER__": _e(_t(lang, "order")),
        "__WHO_H__": _e(_t(lang, "who_h")),
        "__WHO__": "".join(_who(a, lang, hues[a["worker"]]) for a in answers),
        "__LESSONS_H__": _e(_t(lang, "lessons_h")) + f" ({len(data['lessons'])})", "__RECORD_H__": _e(_t(lang, "record_h")),
        "__RECORD_NOTE__": _e(_t(lang, "record_note")), "__HISTORY_H__": _e(_t(lang, "history_h")),
        "__HISTORY_NOTE__": _e(_t(lang, "history_note")), "__EMPTY__": _e(_t(lang, "empty")),
        "__PRIVATE__": _e(_t(lang, "private")), "__MADE__": _e(_t(lang, "made", d=today.isoformat())),
    }
    fill |= {"<!--__PIECES__-->": "".join(parts), "<!--__LESSONS__-->": lessons, "<!--__RATE__-->": "".join(rate),
             "<!--__PICK__-->": pick, "<!--__HISTORY__-->": _history(hist or [], workers, hues, lang),
             "/*__DATA__*/": blob}
    return re.sub(r"<!--__[A-Z]+__-->|/\*__DATA__\*/|__[A-Z_]+__", lambda m: fill.get(m.group(0), m.group(0)), page)


def write(path: str | Path, page: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(page, encoding="utf-8")
    return p
