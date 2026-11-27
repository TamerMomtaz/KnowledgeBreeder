"""The joined process, out again: as a graph.json any kb command reads, and as a plain report in English or Arabic.

Only kb's own words are translated. What people said stays in the words they said it.
"""

from __future__ import annotations

from .join import Process

LABELS = {
    "en": {
        "title": "Work process, joined from what each person said",
        "people": "People: {p}. Steps: {s}. Hand-offs: {h}. Checks: {c}. Decisions: {d}. Questions: {q}.",
        "who": "Who does what", "pipes": "Hand-offs (pipes)", "joins": "Where inputs meet (joins)",
        "tables": "Decision tables (valves)", "checks": "Checks (instruments)", "questions": "Questions worth asking",
        "outside": "outside", "both": "said by both", "one": "said by {w} only",
        "all": "all of", "any": "any of", "unstated": "not said: all of, any of or one of?",
        "if": "If", "then": "then", "otherwise": "Otherwise", "on": "on",
        "none": "None.",
        "q_one_side_send": "{said_by} says they pass \"{thing}\" to {other}. {other} does not say they get it. Ask {other}.",
        "q_one_side_get": "{said_by} says they get \"{thing}\" from {other}. {other} does not say they pass it on. Ask {other}.",
        "q_join": "{step} gets work from {inputs}. Does it need all of them, any of them, or one of them? Ask {person}.",
        "q_no_otherwise": "{person} decides on \"{conds}\" but says nothing about what happens otherwise.",
        "q_unchecked": "Nobody says they check \"{thing}\" when it reaches {person} from {from}.",
        "q_from_whom": "{person} waits for \"{thing}\" but does not say from whom.",
        "q_unsaid_from": "{person} waits for \"{thing}\" without saying from whom; kb joined it to {guess}, who sends it.",
        "q_check_on_nothing": "{person} checks \"{what}\" before saying any work. Which step is that on?",
        "limits": "kb joined these by matching names and words. It does not understand them. "
                  "Read every hand-off and ask the people where a question is open.",
    },
    "ar": {
        "title": "مسار العمل، مجمّعًا مما قاله كل شخص",
        "people": "الأشخاص: {p}. الخطوات: {s}. التسليمات: {h}. الفحوص: {c}. القرارات: {d}. الأسئلة: {q}.",
        "who": "من يفعل ماذا", "pipes": "التسليمات (الأنابيب)", "joins": "حيث تلتقي المدخلات (نقاط الالتقاء)",
        "tables": "جداول القرار (الصمامات)", "checks": "الفحوص (أجهزة القياس)", "questions": "أسئلة تستحق الطرح",
        "outside": "من الخارج", "both": "قالها الطرفان", "one": "قالها {w} فقط",
        "all": "كل من", "any": "أي من", "unstated": "لم يُذكر: كل من، أي من، أم واحد من؟",
        "if": "إذا", "then": "إذن", "otherwise": "وإلا", "on": "على",
        "none": "لا شيء.",
        "q_one_side_send": "يقول {said_by} إنه يسلّم \"{thing}\" إلى {other}، ولا يقول {other} إنه يستلمه. اسأل {other}.",
        "q_one_side_get": "يقول {said_by} إنه يستلم \"{thing}\" من {other}، ولا يقول {other} إنه يسلّمه. اسأل {other}.",
        "q_join": "تصل إلى {step} أعمال من {inputs}. هل تحتاج كلها، أو أيًّا منها، أو واحدًا منها فقط؟ اسأل {person}.",
        "q_no_otherwise": "يقرر {person} بحسب \"{conds}\" ولا يقول ماذا يحدث في غير ذلك.",
        "q_unchecked": "لا أحد يقول إنه يفحص \"{thing}\" عندما يصل إلى {person} من {from}.",
        "q_from_whom": "ينتظر {person} \"{thing}\" ولا يقول ممن.",
        "q_unsaid_from": "ينتظر {person} \"{thing}\" دون أن يقول ممن؛ ربطه kb بـ {guess} الذي يرسله.",
        "q_check_on_nothing": "يفحص {person} \"{what}\" قبل أن يذكر أي عمل. على أي خطوة هذا؟",
        "limits": "جمع kb هذه بمطابقة الأسماء والكلمات، ولا يفهمها. اقرأ كل تسليم واسأل الأشخاص حيث يبقى سؤال مفتوح.",
    },
}


def question_text(q: dict, lang: str = "en") -> str:
    L = LABELS.get(lang, LABELS["en"])
    key = "q_" + q["kind"] + (("_" + q["dir"]) if q["kind"] == "one_side" else "")
    v = dict(q)
    if "inputs" in v:
        v["inputs"] = ", ".join(v["inputs"])
    if "conds" in v:
        v["conds"] = "; ".join(v["conds"])
    return L[key].format(**v)


def _input(pr: Process, src: str, step: str) -> str:
    n = pr.nodes[src]
    who = n.tag if n.type != "Boundary" else n.name
    thing = next((p.thing for p in pr.pipes if p.source == src and p.target == step), "")
    return f"\"{thing}\" ({who})" if thing else who


def to_graph(pr: Process, name: str = "Work process") -> dict:
    """The process as a graph.json in the seed's format: steps are equipment, hand-offs are pipes."""
    nodes, edges = [], []

    def node(nid, type_, kind, tag, label, conf=0.9, **attrs):
        nodes.append({"id": nid, "type": type_, "label": label, "tag": tag, "kind": kind or None, "name": label,
                      "status": "existing", "dexpi_class": None, "sheets": [], "confidence": conf,
                      "attributes": attrs, "provenance": []})

    def edge(s, t, type_, conf=0.9, **attrs):
        edges.append({"id": f"E{len(edges)}", "source": s, "target": t, "type": type_, "confidence": conf,
                      "derived": False, "attributes": attrs, "sheet": None})

    node("PLANT:PROCESS", "Plant", None, None, name)
    for n in pr.nodes.values():
        extra = dict(n.attrs)
        if n.type == "Equipment":
            groups = pr.needs.get(n.id, [])
            extra["needs"] = [{"join": g.join, "from": list(g.inputs)} for g in groups if g.inputs]
        if n.type == "Boundary":
            node(n.id, "Boundary", None, None, n.name, **extra)
        else:
            node(n.id, n.type, n.kind, n.tag, n.name, **extra)
    for a, b in pr.flows:
        edge(a, b, "FLOWS_TO")
    for p in pr.pipes:
        sure = len(p.said_by) > 1
        node(p.id, "PipeSegment", None, None, p.thing, conf=0.9 if sure else 0.6, thing=p.thing, said_by=p.said_by)
        more = {} if sure else {"flow_direction": "inferred"}
        edge(p.source, p.id, "FLOWS_TO", 0.9 if sure else 0.6, **more)
        edge(p.id, p.target, "FLOWS_TO", 0.9 if sure else 0.6, **more)
    for c, s in pr.checks:
        edge(c, s, "MEASURES")
    return {"schema_version": "1.0", "generator": "kb process", "generated_at": None,
            "plant": {"id": "PROCESS", "name": name, "source_file": None}, "nodes": nodes, "edges": edges,
            "stats": {}, "issues": [question_text(q) for q in pr.questions],
            "decision_tables": [{"id": d.id, "person": d.person, "rows": [{"if": c, "then": t} for c, t in d.rows]}
                                for d in pr.decisions]}


def to_markdown(pr: Process, lang: str = "en") -> str:
    L = LABELS.get(lang, LABELS["en"])
    steps = [n for n in pr.nodes.values() if n.type == "Equipment"]
    out = [f"# {L['title']}", "",
           L["people"].format(p=len(pr.people), s=len(steps), h=len(pr.pipes), c=len(pr.checks),
                              d=len(pr.decisions), q=len(pr.questions)), ""]

    out += [f"## {L['who']}", ""]
    for p in pr.people:
        out.append(f"- **{p.name}**" + (f" ({p.job})" if p.job else ""))
        for nid in pr.steps_of(p.name):
            n = pr.nodes[nid]
            if n.type == "Equipment":
                j = n.attrs.get("join")
                out.append(f"  - {n.tag}: {n.name}" + (f"  [{L[j]}]" if j else ""))
    out.append("")

    out += [f"## {L['pipes']}", ""]
    for p in pr.pipes:
        s, t = pr.nodes[p.source], pr.nodes[p.target]
        sname = s.tag if s.type != "Boundary" else f"{s.name} ({L['outside']})"
        tname = t.tag if t.type != "Boundary" else f"{t.name} ({L['outside']})"
        said = L["both"] if len(p.said_by) > 1 else L["one"].format(w=p.said_by[0])
        out.append(f"- {sname} → \"{p.thing}\" → {tname}  ({said})")
    out += [L["none"]] if not pr.pipes else []
    out.append("")

    out += [f"## {L['joins']}", ""]
    joins = [(nid, g) for nid, gs in pr.needs.items() for g in gs
             if pr.nodes[nid].type == "Equipment" and len(g.inputs) > 1]
    for nid, g in joins:
        out.append(f"- {pr.nodes[nid].tag}: {L.get(g.join, g.join)}: " + ", ".join(_input(pr, i, nid) for i in g.inputs))
    out += [L["none"]] if not joins else []
    out.append("")

    out += [f"## {L['tables']}", ""]
    for d in pr.decisions:
        out += [f"**{d.person}** ({pr.nodes[d.id].tag})", "", f"| {L['if']} | {L['then']} |", "|---|---|"]
        for c, t in d.rows:
            out.append(f"| {c or L['otherwise']} | {t} |")
        out.append("")
    out += [L["none"], ""] if not pr.decisions else []

    out += [f"## {L['checks']}", ""]
    for c, s in pr.checks:
        out.append(f"- {pr.nodes[c].tag}: {pr.nodes[c].name} ({L['on']} {pr.nodes[s].tag})")
    out += [L["none"]] if not pr.checks else []
    out.append("")

    out += [f"## {L['questions']}", ""]
    out += [f"{i}. {question_text(q, lang)}" for i, q in enumerate(pr.questions, 1)] or [L["none"]]
    out += ["", L["limits"]]
    return "\n".join(out)
