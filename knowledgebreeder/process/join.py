"""Join what each person said into one process, drawn the way a plant is drawn.

    a step        a piece of work one person does                 drawn as equipment
    a pipe        a hand-off: a thing passed from one person on   drawn as a pipe, named by the thing
    a valve       a decision that sends the work one way or other drawn as a component of kind "decision"
    an instrument a check someone makes on the work               drawn as an instrument on that step
    a boundary    someone named who gave no description           a source if they give, a sink if they get
    a join        how a step's inputs combine: all of, any of, one of

The result is a graph.json in the plant graph's own format, so `kb walk`, `kb stats` and `kb whatif` work on it.
`stops()` here goes further than `kb whatif`: it honours the join types, so a step that needs any one of two
inputs keeps going when one of them stops.

A hand-off said by both sides is drawn solid. One said by one side only is drawn dashed and listed as a question,
because only the other person can say whether it is true. Nothing here is guessed silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .speech import Person, Sentence, norm, vague, words


@dataclass
class Node:
    id: str
    type: str                  # Equipment, Component, Instrument, Boundary, PipeSegment
    kind: str
    tag: str
    name: str
    person: str = ""
    line: int = 0
    attrs: dict = field(default_factory=dict)


@dataclass
class Pipe:
    id: str
    thing: str
    source: str                # node id of the sender's step (or an outside party)
    target: str                # node id of the receiver's step (or an outside party)
    said_by: list[str]         # who said it: one name, or both


@dataclass
class Group:
    join: str                  # all, any, one, or "unstated" (several inputs, no join word said)
    inputs: list[str]


@dataclass
class Decision:
    id: str
    person: str
    rows: list[tuple[str, str]]   # (condition, what is done); condition "" means otherwise
    line: int = 0


@dataclass
class Process:
    people: list[Person]
    nodes: dict[str, Node] = field(default_factory=dict)
    flows: list[tuple[str, str]] = field(default_factory=list)     # one person's own work, step to step
    pipes: list[Pipe] = field(default_factory=list)
    needs: dict[str, list[Group]] = field(default_factory=dict)    # step id -> what it needs to go
    checks: list[tuple[str, str]] = field(default_factory=list)    # (instrument id, step id it measures)
    decisions: list[Decision] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)

    def label(self, nid: str) -> str:
        n = self.nodes[nid]
        return f"{n.tag}: {n.name}" if n.type != "Boundary" else n.name

    def steps_of(self, person: str) -> list[str]:
        return [n.id for n in self.nodes.values() if n.person == person and n.type in ("Equipment", "Component")]


@dataclass
class _Inlet:                  # a place where a person says something arrives
    step: str
    thing: str
    who: str
    group: Group
    person: str
    matched: bool = False


def _slug(s: str) -> str:
    return "-".join(norm(s).split()) or "x"


def join(people: list[Person]) -> Process:
    pr = Process(people)
    seen: dict[str, int] = {}
    for p in people:                      # two files for one name: keep both, told apart
        k = _slug(p.name)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            p.name = f"{p.name} ({seen[k]})"
    known = {}
    for p in people:
        for k in p.names():
            known.setdefault(k, p.name)

    def whom(who: str) -> str | None:
        k = norm(who)
        if k in known:
            return known[k]
        hits = {v for n, v in known.items() if n and (n in k.split() or k in n.split())}
        return hits.pop() if len(hits) == 1 else None

    inlets: list[_Inlet] = []
    outlets: list[tuple[str, Sentence, str]] = []        # (step, send sentence, person)

    for p in people:
        n_step, n_check, prev, pending_checks = 0, 0, [], []
        decision: Decision | None = None
        dnode: str | None = None
        branches: list[str] = []

        def add_step(s: Sentence, after: list[str], how: str = "all") -> str:
            nonlocal n_step
            n_step += 1
            nid = f"STEP:{_slug(p.name)}:{n_step}"
            pr.nodes[nid] = Node(nid, "Equipment", "step", f"{p.name} {n_step}", _plain(s.text), p.name, s.line,
                                 {"said": s.text, "person": p.name, "job": p.job})
            groups = pr.needs.setdefault(nid, [])
            if after:
                groups.append(Group(how if len(after) > 1 else "all", list(after)))
                pr.flows += [(a, nid) for a in after]
            if s.kind == "get":
                g = Group("all", [])
                groups.append(g)
                inlets.append(_Inlet(nid, s.thing, s.who, g, p.name))
            elif s.kind == "wait":
                g = Group(s.join, [])
                groups.append(g)
                pr.nodes[nid].attrs["join"] = s.join
                inlets.extend(_Inlet(nid, t, w, g, p.name) for t, w in s.items)
            elif s.kind == "send":
                outlets.append((nid, s, p.name))
            for c in pending_checks:
                pr.checks.append((c, nid))
            pending_checks.clear()
            return nid

        def close_decision():
            nonlocal decision, dnode, branches, prev
            if decision is not None:
                pr.decisions.append(decision)
                prev = branches
            decision, dnode, branches = None, None, []

        for s in p.sentences:
            if s.kind in ("if", "else"):
                if s.kind == "if" and decision is not None and any(c == "" for c, _ in decision.rows):
                    close_decision()
                if decision is None:
                    n_step += 1
                    dnode = f"DECIDE:{_slug(p.name)}:{n_step}"
                    pr.nodes[dnode] = Node(dnode, "Component", "decision", f"{p.name} {n_step}",
                                           "decides", p.name, s.line, {"person": p.name})
                    pr.needs[dnode] = [Group("one" if len(prev) > 1 else "all", list(prev))] if prev else []
                    pr.flows += [(a, dnode) for a in prev]
                    decision = Decision(dnode, p.name, [], s.line)
                inner = s.then or Sentence("step", s.text, s.line)
                b = add_step(inner, [dnode])
                branches.append(b)
                decision.rows.append((s.cond if s.kind == "if" else "", pr.label(b)))
                continue
            close_decision()
            if s.kind == "check":
                n_check += 1
                cid = f"CHECK:{_slug(p.name)}:{n_check}"
                pr.nodes[cid] = Node(cid, "Instrument", "check", f"{p.name} ✓{n_check}", s.thing, p.name,
                                     s.line, {"variable": s.thing, "said": s.text, "person": p.name})
                if prev:
                    pr.checks += [(cid, a) for a in prev]
                else:
                    pending_checks.append(cid)
                continue
            prev = [add_step(s, prev, "one")]
        close_decision()
        for c in pending_checks:
            pr.questions.append({"kind": "check_on_nothing", "person": p.name, "what": pr.nodes[c].name})

    _connect(pr, inlets, outlets, whom)
    _ask(pr)
    return pr


def _plain(text: str) -> str:
    for lead in ("I ", "i ", "Then I ", "then I ", "And I ", "أنا "):
        if text.startswith(lead):
            return text[len(lead):]
    return text


def _same_thing(a: str, b: str) -> bool:
    return vague(a) or vague(b) or bool(words(a) & words(b))


def _connect(pr: Process, inlets: list[_Inlet], outlets: list, whom) -> None:
    outside: dict[tuple[str, str], str] = {}

    def party(who: str, direction: str) -> str:
        name = who.strip() or "someone unnamed"
        key = (norm(name), direction)
        if key not in outside:
            nid = f"BOUNDARY:{_slug(name)}:{'in' if direction == 'source' else 'out'}"
            pr.nodes[nid] = Node(nid, "Boundary", "", name, name, "", 0, {"direction": direction, "outside": True})
            outside[key] = nid
        return outside[key]

    def pipe(thing: str, src: str, dst: str, said: list[str], group: Group | None):
        pid = f"PIPE:{len(pr.pipes) + 1}"
        pr.pipes.append(Pipe(pid, thing, src, dst, said))
        if group is not None:
            group.inputs.append(src)
        else:
            # an outside party that only gets things is left waiting only when everything sent to it stops
            how = "any" if pr.nodes[dst].type == "Boundary" else "unstated"
            gs = pr.needs.setdefault(dst, [])
            extra = next((g for g in gs if g.join == how), None)
            if extra is None:
                extra = Group(how, [])
                gs.append(extra)
            extra.inputs.append(src)

    for step, s, sender in outlets:
        to = whom(s.who)
        if to is None:
            pipe(s.thing, step, party(s.who, "sink"), [sender], None)
            continue
        cands = [i for i in inlets if i.person == to and not i.matched and _same_thing(s.thing, i.thing)
                 and (not i.who or whom(i.who) == sender)]
        named = [i for i in cands if i.who]
        hit = (named or cands or [None])[0]
        if hit is not None:
            hit.matched = True
            thing = hit.thing if vague(s.thing) else s.thing
            pipe(thing, step, hit.step, [sender, to] if hit.who else [sender], hit.group)
            if not hit.who:
                pr.questions.append({"kind": "unsaid_from", "person": to, "thing": hit.thing, "guess": sender})
        else:
            first = pr.steps_of(to)
            target = first[0] if first else party(s.who, "sink")
            pipe(s.thing, step, target, [sender], None)
            pr.questions.append({"kind": "one_side", "said_by": sender, "thing": s.thing, "other": to,
                                 "said": s.text, "dir": "send"})

    for i in inlets:
        if i.matched:
            continue
        frm = whom(i.who) if i.who else None
        if frm is None:
            pipe(i.thing, party(i.who, "source"), i.step, [i.person], i.group)
            if not i.who:
                pr.questions.append({"kind": "from_whom", "person": i.person, "thing": i.thing})
            continue
        steps = [n for n in pr.steps_of(frm) if pr.nodes[n].type == "Equipment"]
        src = steps[-1] if steps else party(i.who, "source")
        pipe(i.thing, src, i.step, [i.person], i.group)
        pr.questions.append({"kind": "one_side", "said_by": i.person, "thing": i.thing, "other": frm,
                             "dir": "get"})


def _ask(pr: Process) -> None:
    for nid, groups in pr.needs.items():
        for g in groups:
            if g.join == "unstated" and (len(g.inputs) > 1 or sum(len(x.inputs) for x in groups) > 1):
                pr.questions.append({"kind": "join", "person": pr.nodes[nid].person, "step": pr.nodes[nid].tag,
                                     "inputs": [_from(pr, i) for x in groups for i in x.inputs]})
    for d in pr.decisions:
        if not any(c == "" for c, _ in d.rows):
            pr.questions.append({"kind": "no_otherwise", "person": d.person,
                                 "conds": [c for c, _ in d.rows]})
    checked = {s for _c, s in pr.checks}
    for p in pr.pipes:
        dst = pr.nodes[p.target]
        if dst.type == "Equipment" and p.target not in checked and not _checked_later(pr, p.target, checked):
            pr.questions.append({"kind": "unchecked", "person": dst.person, "thing": p.thing,
                                 "from": _from(pr, p.source)})


def _checked_later(pr: Process, step: str, checked: set[str]) -> bool:
    """A check said right after the step that receives the thing counts as checking it."""
    nxt = [b for a, b in pr.flows if a == step]
    return any(n in checked for n in nxt[:1])


def _from(pr: Process, nid: str) -> str:
    n = pr.nodes[nid]
    return n.person or n.name


# ------------------------------------------------------------------ what if

def stops(pr: Process, failed: set[str]) -> set[str]:
    """Every step that stops when the given nodes stop, honouring all of / any of / one of.

    "all of", and a join nobody stated, stop when any input stops. "any of" and "one of" stop only when every input
    stops. A check stops with the step it is on.
    """
    down = set(failed)
    changed = True
    while changed:
        changed = False
        for nid, groups in pr.needs.items():
            if nid in down:
                continue
            for g in groups:
                if not g.inputs:
                    continue
                gone = [i in down for i in g.inputs]
                if (all(gone) if g.join in ("any", "one") else any(gone)):
                    down.add(nid)
                    changed = True
                    break
    for c, s in pr.checks:
        if s in down:
            down.add(c)
    return down


def find(pr: Process, what: str) -> set[str]:
    """A person (by name, job or another name they go by) gives all their steps; a step tag gives that step."""
    k = norm(what)
    for p in pr.people:
        if k in p.names():
            return set(pr.steps_of(p.name))
    hits = {n.id for n in pr.nodes.values() if norm(n.tag) == k or n.id == what}
    if not hits:
        hits = {n.id for n in pr.nodes.values() if n.type == "Boundary" and norm(n.name) == k}
    if not hits:
        raise KeyError(f"no person or step called '{what}'")
    return hits


def whatif(pr: Process, what: str) -> dict:
    failed = find(pr, what)
    down = stops(pr, failed) - failed
    kept = []
    for nid, groups in pr.needs.items():
        if nid in down or nid in failed:
            continue
        for g in groups:
            if g.join in ("any", "one") and any(i in failed | down for i in g.inputs):
                kept.append(pr.label(nid))
    return {
        "stops": what,
        "also_stop": sorted(pr.label(n) for n in down if pr.nodes[n].type in ("Equipment", "Component")),
        "outside_left_waiting": sorted(pr.nodes[n].name for n in down if pr.nodes[n].type == "Boundary"),
        "checks_lost": sorted(pr.nodes[n].tag for n in down if pr.nodes[n].type == "Instrument"),
        "kept_going_by_another_input": sorted(set(kept)),
        "people_hit": sorted({pr.nodes[n].person for n in down
                              if pr.nodes[n].person and pr.nodes[n].type in ("Equipment", "Component")}),
    }

