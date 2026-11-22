"""The trail of an advice run: who did what, step by step, in the eight fields of a Vn-trail.

The Vn-Trail is a method for showing who did what in work done by a person and an AI together: one entry per
substantive change, each with the same eight fields (Momtaz, 2026, "The Vn-Trail: A Method for Inspectable
Human-AI Collaboration in Scholarly Work", SSRN 6739158). An advice run is such a work. You give the cards, the
lessons and the ask; each model writes its pieces; you judge them, change some, and pick one answer. kb records
all of it in the run log as it happens, so the trail is read from records, not remembered afterwards.

Origin says who started each move: HUMAN, AI, or DIALOGUE when your change reframed a model's idea, which
neither of you would have written alone. A run that still waits on your verdict ends with a "forthcoming" entry:
the trail claims to be faithful, not complete.

    kb picture trail                newest advice run, as a table
    kb picture trail RUN --json     one entry per line, for coding many trails at once
    kb picture trail --all --json   every advice run
"""

from __future__ import annotations

from collections import Counter

FIELDS = ("n", "trigger", "delta_plus", "delta_minus", "delta_reframed", "origin", "rationale", "split")
ORIGINS = ("HUMAN", "AI", "DIALOGUE")
SHORT = 90              # characters of a piece's move quoted in an entry

T = {
    "en": {
        "n": "Vn", "trigger": "Trigger", "delta_plus": "Δ+ added", "delta_minus": "Δ− removed",
        "delta_reframed": "Δ± reframed", "origin": "Origin", "rationale": "Rationale", "split": "Carbon / silicon",
        "none": "none",
        "ask_n": "V0: the ask", "ask_trigger": "you ran kb picture advise",
        "ask_plus": "{lines} lines from your cards and {lessons} of your lessons, sent to {models}",
        "ask_minus": "{n} lines left out: they did not fit", "ask_held": "{n} lines kept on this machine: private",
        "ask_why": "advice on: {subject}",
        "ask_split": "carbon: the cards, the lessons and the ask. silicon: nothing yet.",
        "ans_n": "V{i}: {w}'s answer", "ans_trigger": "kb asked {w} ({model}, {where})",
        "ans_plus": "{k} pieces: {list}", "ans_minus": "{d} pieces dropped by kb's checks: they cited no line kb sent",
        "ans_orders": "{d} pieces dropped: they rested only on lines that read like instructions to a model",
        "ans_why": "advice held to the cited lines of your cards", "ans_failed": "no answer: {e}",
        "ans_split": "silicon: {w} wrote {k} pieces. carbon: none in this step.",
        "ver_n": "V{i}: your verdict on {w}", "ver_trigger": "you read the pieces",
        "ver_plus": "you would act on {list}", "ver_minus": "you would not act on {list}",
        "ver_reframed": "you changed {list} (next entries)", "ver_why": "no reason given",
        "ver_split": "carbon: the verdict. silicon: the pieces judged.",
        "chg_n": "V{i}: your change to {w} #{k}", "chg_trigger": "{w}'s piece #{k}",
        "chg_reframed": "from “{old}” to “{new}”", "chg_plus": "a lesson for every run",
        "chg_split": "silicon: the first idea. carbon: the reframe.",
        "pick_n": "V{i}: your pick", "pick_trigger": "you compared the answers", "pick_plus": "picked {w}",
        "pick_minus": "not {list}", "pick_why": "a separate vote from the ticks", "pick_split": "carbon: the choice.",
        "open_n": "forthcoming", "open_plus": "waiting on your verdict: {list}",
        "here": "on this machine", "network": "on your network", "outside": "outside this machine",
        "whole": "your whole picture",
    },
    "ar": {
        "n": "Vn", "trigger": "ما بدأها", "delta_plus": "Δ+ أضيف", "delta_minus": "Δ− حُذف",
        "delta_reframed": "Δ± أُعيدت صياغته", "origin": "المصدر", "rationale": "السبب", "split": "كربون / سيليكون",
        "none": "لا شيء",
        "ask_n": "V0: الطلب", "ask_trigger": "شغّلت kb picture advise",
        "ask_plus": "أسطر من بطاقاتك: {lines}، ومن دروسك: {lessons}، أُرسلت إلى {models}",
        "ask_minus": "أسطر لم تتسع: {n}", "ask_held": "أسطر بقيت على هذا الجهاز لأنها خاصة: {n}",
        "ask_why": "نصيحة في: {subject}",
        "ask_split": "كربون: البطاقات والدروس والطلب. سيليكون: لا شيء بعد.",
        "ans_n": "V{i}: إجابة {w}", "ans_trigger": "سأل kb النموذج {w} ({model}، {where})",
        "ans_plus": "عدد النصائح: {k}: {list}", "ans_minus": "نصائح أسقطتها فحوص kb لأنها لم تستند إلى سطر أرسله: {d}",
        "ans_orders": "نصائح أُسقطت لأنها استندت فقط إلى أسطر تشبه أوامر لنموذج: {d}",
        "ans_why": "نصيحة مقيدة بالأسطر المذكورة من بطاقاتك", "ans_failed": "لا إجابة: {e}",
        "ans_split": "سيليكون: كتب {w} نصائح عددها {k}. كربون: لا شيء في هذه الخطوة.",
        "ver_n": "V{i}: حكمك على {w}", "ver_trigger": "قرأت النصائح",
        "ver_plus": "ستعمل بـ {list}", "ver_minus": "لن تعمل بـ {list}",
        "ver_reframed": "غيّرت {list} (في الخطوات التالية)", "ver_why": "بلا سبب مكتوب",
        "ver_split": "كربون: الحكم. سيليكون: النصائح المحكوم عليها.",
        "chg_n": "V{i}: تغييرك على {w} #{k}", "chg_trigger": "نصيحة {w} رقم {k}",
        "chg_reframed": "من «{old}» إلى «{new}»", "chg_plus": "درس لكل تشغيل",
        "chg_split": "سيليكون: الفكرة الأولى. كربون: إعادة الصياغة.",
        "pick_n": "V{i}: اختيارك", "pick_trigger": "قارنت الإجابات", "pick_plus": "اخترت {w}",
        "pick_minus": "وليس {list}", "pick_why": "تصويت منفصل عن العلامات", "pick_split": "كربون: الاختيار.",
        "open_n": "forthcoming", "open_plus": "في انتظار حكمك: {list}",
        "here": "على هذا الجهاز", "network": "على شبكتك", "outside": "خارج هذا الجهاز",
        "whole": "صورتك الكاملة",
    },
}


def _t(lang: str, key: str, **v) -> str:
    """In Arabic each filled-in value is isolated, so a name or a list of numbers keeps its own order."""
    s = T[lang][key]
    for k, x in v.items():
        s = s.replace("{" + k + "}", f"\u2068{x}\u2069" if lang == "ar" else str(x))
    return s


def _short(text: str) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= SHORT else text[: SHORT - 1].rstrip() + "…"


def _nums(ns) -> str:
    return ", ".join(f"#{n}" for n in ns)


def entries(data: dict, lang: str = "en") -> list[dict]:
    """The trail of one advice run, from what ``page.gather`` read out of the run log."""
    lang = lang if lang in T else "en"
    none = _t(lang, "none")
    answers = data["answers"]

    def entry(n, trigger, plus, minus, reframed, origin, why, split):
        return dict(zip(FIELDS, (n, trigger, plus or none, minus or none, reframed or none, origin, why or none,
                                 split), strict=True))

    first = next((a for a in answers if "error" not in a), answers[0] if answers else {})
    held = max((a.get("held") or 0 for a in answers), default=0)
    out = [entry(_t(lang, "ask_n"), _t(lang, "ask_trigger"),
                 _t(lang, "ask_plus", lines=first.get("lines_sent", 0), lessons=len(data["lessons"]),
                    models=", ".join(a["worker"] for a in answers) or none),
                 "; ".join(x for x in (_t(lang, "ask_minus", n=first["left_out"]) if first.get("left_out") else "",
                                       _t(lang, "ask_held", n=held) if held else "") if x), "", "HUMAN",
                 _t(lang, "ask_why", subject=data.get("subject") or _t(lang, "whole")), _t(lang, "ask_split"))]
    i = 0
    for a in answers:
        i += 1
        where = _t(lang, a["where"]) if a.get("where") else none
        trig = _t(lang, "ans_trigger", w=a["worker"], model=a.get("model") or none, where=where)
        if "error" in a:
            out.append(entry(_t(lang, "ans_n", i=i, w=a["worker"]), trig, "", "", "", "AI",
                             _t(lang, "ans_failed", e=a["error"]), _t(lang, "ans_split", w=a["worker"], k=0)))
            continue
        k = len(a["pieces"])
        out.append(entry(_t(lang, "ans_n", i=i, w=a["worker"]), trig,
                         _t(lang, "ans_plus", k=k, list="; ".join(f'#{p["n"]} {_short(p.get("move"))}' for p in a["pieces"])),
                         "; ".join(x for x in (_t(lang, "ans_minus", d=a["dropped"]) if a.get("dropped") else "",
                                               _t(lang, "ans_orders", d=a["dropped_orders"])
                                               if a.get("dropped_orders") else "") if x), "", "AI",
                         _t(lang, "ans_why"), _t(lang, "ans_split", w=a["worker"], k=k)))
    waiting = []
    for a in answers:
        if "error" in a or not a["pieces"]:
            continue
        if a["would_act"] is None:
            waiting.append(a["worker"])
            continue
        act = a["rated"] or []
        changed = [p for p in a["pieces"] if p.get("change")]
        i += 1
        out.append(entry(_t(lang, "ver_n", i=i, w=a["worker"]), _t(lang, "ver_trigger"),
                         _t(lang, "ver_plus", list=_nums(act)) if act else "",
                         _t(lang, "ver_minus", list=_nums(p["n"] for p in a["pieces"] if p["n"] not in act))
                         if len(act) < len(a["pieces"]) else "",
                         _t(lang, "ver_reframed", list=_nums(p["n"] for p in changed)) if changed else "", "HUMAN",
                         a.get("why") or _t(lang, "ver_why"), _t(lang, "ver_split")))
        for p in changed:
            i += 1
            out.append(entry(_t(lang, "chg_n", i=i, w=a["worker"], k=p["n"]), _t(lang, "chg_trigger", w=a["worker"], k=p["n"]),
                             _t(lang, "chg_plus") if p.get("kept") else "", "",
                             _t(lang, "chg_reframed", old=_short(p.get("move")), new=p["change"]), "DIALOGUE",
                             a.get("why") or "", _t(lang, "chg_split")))
    chosen = next((a["worker"] for a in answers if a.get("picked") == 1.0), None)
    if chosen:
        i += 1
        rest = [a["worker"] for a in answers if a.get("picked") is not None and a["worker"] != chosen]
        out.append(entry(_t(lang, "pick_n", i=i), _t(lang, "pick_trigger"), _t(lang, "pick_plus", w=chosen),
                         _t(lang, "pick_minus", list=", ".join(rest)) if rest else "", "", "HUMAN",
                         _t(lang, "pick_why"), _t(lang, "pick_split")))
    if waiting:                                 # an open trail claims fidelity, not completeness
        out.append(dict.fromkeys(FIELDS, "") | {"n": _t(lang, "open_n"),
                                                "delta_plus": _t(lang, "open_plus", list=", ".join(waiting))})
    return out


def origins(trail: list[dict]) -> dict[str, int]:
    """How many entries each party started: the distribution the Vn-Trail reads as the shape of the work."""
    c = Counter(e["origin"] for e in trail)
    return {o: c.get(o, 0) for o in ORIGINS}


def markdown(trail: list[dict], run: str, lang: str = "en") -> str:
    lang = lang if lang in T else "en"
    o = origins(trail)
    head = "| " + " | ".join(_t(lang, f) for f in FIELDS) + " |"
    rows = ["| " + " | ".join(str(e[f]).replace("|", "/").replace("\n", " ") for f in FIELDS) + " |" for e in trail]
    return (f"# Vn-trail: {run}\n\n" + " · ".join(f"{k} {v}" for k, v in o.items()) + "\n\n"
            + "\n".join([head, "|" + "---|" * len(FIELDS)] + rows) + "\n")
