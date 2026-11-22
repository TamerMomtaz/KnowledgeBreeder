"""A register of your agents: one record each, like a staff file, and what in it needs a person's look.

An agent is any program that reads your data and does something with it on its own: a bot that answers customers,
a script that posts a weekly report, a model that writes code, kb's own models. You keep the register in one private
Markdown file, work/agents.md, one block per agent, written the way you would say it:

    name: Shop replier
    does: answers questions on the shop page
    runs: outside (a hosting service)
    reads: customer messages; the price list
    sends: api.example-model.com
    keys: SHOP_MODEL_KEY
    may: send
    ratifies: nobody
    owner: Nour
    stop: switch off the page's chat box
    passes: Order reminder
    last_run: 2026-11-18

Every field but the name is optional, and an empty one is shown as not written. A key is written by its variable's
name, never its value: a file that holds what looks like a real key is refused. kb adds a record for each model in
your models file by itself, with its last run read from the run log.

The fields follow the five layers of ARM, Agent Resource Management (Momtaz, 2026, "AIAIRS & ARM", SSRN 6380498):
the owner is the accountability chain; the register itself is the stewardship register; who ratifies is the
prospective review; how to stop it is the override protocol; whom it passes work to is the inter-agent council.
What needs a look is a gap in one of those layers:

    no owner                        nobody answers for it
    acts with nobody ratifying      it may send, pay, change or delete with no person's yes first
    data leaves with nobody's yes   it, or an agent it passes work to, sends outside this machine and your network
    no way to stop it written       it acts or sends outside, and nobody wrote how to stop it
    reads your private names        it reads a name on your private list, and its work leaves
    quiet but holding keys          it has not run for a long time and still holds keys: retire it or revoke them
    a shared key                    two agents use one key, so revoking it for one stops both
    passes to an unknown agent      it hands work to an agent that has no record here

kb reads what you wrote. It does not inspect the agents, so a record is only as true as its writer.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .models import HERE, NETWORK, OUTSIDE, ModelError, place
from .picture.private import Private

DEFAULT_PATH = "work/agents.md"
NOT_WRITTEN = "not written"
FIELDS = ("name", "does", "runs", "reads", "sends", "keys", "may", "ratifies", "owner", "stop", "passes", "last_run")
ALIASES = {"purpose": "does", "where": "runs", "runs on": "runs", "sends to": "sends", "data goes to": "sends",
           "goes to": "sends", "secrets": "keys", "key": "keys", "can": "may", "may do": "may", "signs": "ratifies",
           "signed by": "ratifies", "approved by": "ratifies", "approves": "ratifies", "reviewed by": "ratifies", "ratified by": "ratifies", "checked by": "ratifies", "who signs": "ratifies",
           "responsible": "owner", "answers for it": "owner", "how to stop": "stop", "stop it": "stop",
           "hands to": "passes", "passes to": "passes", "last run": "last_run", "last ran": "last_run"}
ACTS = ("send", "post", "publish", "pay", "buy", "order", "book", "change", "edit", "write", "delete", "remove",
        "merge", "push", "commit", "deploy", "email", "message", "reply", "train", "transfer")
NOBODY = {"", "nobody", "no one", "noone", "none", "-", "unknown", NOT_WRITTEN, "لا أحد"}
NOWHERE = {"nowhere", "none", "nothing", "-", "no", "لا مكان"}
_OUT_WORDS = re.compile(r"\b(?:outside|cloud|internet|online|hosted|hosting)\b|خارج", re.IGNORECASE)
_HERE_WORDS = re.compile(r"\b(?:this machine|this laptop|my laptop|laptop|locally|local|here|localhost)\b|هذا الجهاز", re.IGNORECASE)
_NET_WORDS = re.compile(r"\b(?:my network|our network|network|lan|tailnet|tailscale|tower|home server)\b|شبكتي", re.IGNORECASE)
_HOST = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:/\S*)?|\b(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE)
_KEY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
QUIET_DAYS = 90

TEMPLATE = """# Your agents: one block per agent, never committed. Lines that start with # are notes and are skipped.
#
# Copy the block below, remove the # marks, and fill in what you know. Only the name is needed.
# A key goes in by its variable's name, never its value.
#
# name:
# does:       what it is for, in one line
# runs:       this machine, my network, or outside (or its address)
# reads:      what data it reads, separated by ;
# sends:      where its work or your data goes, separated by ; (nowhere, if nowhere)
# keys:       the names of the variables that hold its keys
# may:        what it may do by itself: advise, draft, send, post, pay, change, delete, merge, deploy
# ratifies:   who checks its work before it acts (nobody, if nobody)
# owner:      who answers for it
# stop:       how to stop it
# passes:     other agents it hands its work to, separated by ;
# last_run:   YYYY-MM-DD
"""


@dataclass
class Agent:
    name: str
    does: str = ""
    runs: str = ""
    reads: list[str] = field(default_factory=list)
    sends: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    may: list[str] = field(default_factory=list)
    ratifies: str = ""
    owner: str = ""
    stop: str = ""
    passes: list[str] = field(default_factory=list)
    last_run: str = ""
    origin: str = "your file"           # or "kb's models file"
    line: int = 0

    @property
    def where(self) -> str:
        return where(self.runs) if self.runs else ""

    @property
    def acts(self) -> list[str]:
        """What it may do by itself that changes something in the world."""
        return [m for m in self.may if any(re.search(rf"\b{v}", m, re.IGNORECASE) for v in ACTS)]

    @property
    def ratified(self) -> bool:
        return self.ratifies.strip().lower() not in NOBODY

    def out(self) -> list[str]:
        """Where its work goes that is outside this machine and your network, as written."""
        dests = [d for d in self.sends if d.strip().lower() not in NOWHERE]
        return [d for d in dests if where(d) == OUTSIDE]


def where(text: str) -> str:
    """this machine, your network or outside, for how a place is written. An address is placed by the same rule as
    kb's gate; words are read as written, and a name kb cannot place counts as outside."""
    t = (text or "").strip()
    if not t:
        return ""
    if t.lower() in NOWHERE:
        return HERE
    if _OUT_WORDS.search(t):
        return OUTSIDE
    if _NET_WORDS.search(t):
        return NETWORK
    m = _HOST.search(t)
    if m:
        url = m.group(0) if m.group(0).lower().startswith("http") else "http://" + m.group(0)
        try:
            return place(url)[1]
        except ModelError:
            return OUTSIDE
    if _HERE_WORDS.search(t):
        return HERE
    return OUTSIDE


def _list(v: str) -> list[str]:
    return [x for x in (" ".join(p.split()) for p in re.split(r"[;،]|,(?![^()]*\))", v)) if x]


def parse(text: str, source: str = DEFAULT_PATH) -> list[Agent]:
    """The agents in a register file. Raises KeyError on a line that looks like a real key, or a block with no name."""
    out: list[Agent] = []
    cur: dict | None = None
    guard = Private()
    for n, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith(("#", "<!--")):
            continue
        if "key or token" in guard.kinds(s):
            raise KeyError(f"line {n} of {source} holds what looks like a real key. Remove it now, and write only "
                           f"the name of the variable that holds it, for example keys: SHOP_MODEL_KEY.")
        s = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", s)
        k, sep, v = s.partition(":")
        k = " ".join(k.lower().split())
        k = ALIASES.get(k, k)
        if not sep or k not in FIELDS:
            continue
        v = " ".join(v.split())
        if k == "name":
            if cur:
                out.append(_agent(cur))
            cur = {"name": v, "line": n}
            if not v:
                raise KeyError(f"line {n} of {source} starts an agent with no name.")
            continue
        if cur is None:
            raise KeyError(f"line {n} of {source} says '{k}' before any 'name:'. Start each agent with its name.")
        cur[k] = v
    if cur:
        out.append(_agent(cur))
    seen: set[str] = set()
    for a in out:
        if a.name.casefold() in seen:
            raise KeyError(f"{source} names the agent '{a.name}' twice (line {a.line}). Give each its own name.")
        seen.add(a.name.casefold())
        bad = [k for k in a.keys if not _KEY_NAME.match(k)]
        if bad:
            raise KeyError(f"line {a.line} of {source}: '{bad[0]}' is not a variable name. Write only the name of the "
                           f"variable that holds the key, for example SHOP_MODEL_KEY.")
    return out


def _agent(d: dict) -> Agent:
    lists = {k: _list(d.get(k, "")) for k in ("reads", "sends", "keys", "may", "passes")}
    return Agent(name=d["name"], does=d.get("does", ""), runs=d.get("runs", ""), ratifies=d.get("ratifies", ""),
                 owner=d.get("owner", ""), stop=d.get("stop", ""), last_run=d.get("last_run", ""), line=d["line"],
                 **lists)


def read(path: str | Path) -> list[Agent]:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8"), str(p)) if p.is_file() else []


def from_models(book, last: dict[str, str] | None = None) -> list[Agent]:
    """One record per model in kb's models file. kb only advises; you ratify each run that leaves (--allow) and every
    piece by your ticks, and it runs only when you type kb."""
    out = []
    for name, m in book.models.items():
        host, at = place(m.url)
        out.append(Agent(name=f"kb: {name}", does=f"writes advice and reads saved sources with {m.model}",
                         runs=f"{at} ({host})" if at != HERE else HERE, reads=["your cards", "your lessons",
                                                                               "saved sources"],
                         sends=[] if at == HERE else [host], keys=[m.key_env] if m.key_env else [], may=["advise"],
                         ratifies="you: --allow for each run that leaves this machine, and your ticks",
                         owner="you", stop="it runs only when you type kb", last_run=(last or {}).get(name, ""),
                         origin="kb's models file"))
    return out


def last_runs(db_path: str | Path) -> dict[str, str]:
    """The date each worker last worked, from the run log. No log means no dates."""
    if not Path(db_path).is_file():
        return {}
    from .runlog import RunLog
    log = RunLog(db_path)
    try:
        rows = log.db.execute("SELECT worker, MAX(started) AS last FROM steps WHERE worker IS NOT NULL GROUP BY worker")
        return {r["worker"]: (r["last"] or "")[:10] for r in rows}
    finally:
        log.close()


def _date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def _reach(a: Agent, by: dict[str, Agent]) -> list[tuple[str, list[str]]]:
    """(destination outside, the agents its work passes through to get there), following passes, each agent once."""
    out, seen, todo = [], {a.name.casefold()}, [(a, [])]
    while todo:
        cur, path = todo.pop(0)
        out += [(d, path) for d in cur.out()]
        for nxt in cur.passes:
            b = by.get(nxt.casefold())
            if b and b.name.casefold() not in seen:
                seen.add(b.name.casefold())
                todo.append((b, [*path, b.name]))
    return out


def review(agents: list[Agent], today: date, private: Private | None = None, quiet_days: int = QUIET_DAYS) -> list[dict]:
    """What needs a person's look, the most serious first: one finding per gap, with the ARM layer it belongs to."""
    by = {a.name.casefold(): a for a in agents}
    found: list[dict] = []

    def add(a: Agent, rank: int, what: str, layer: str, fix: str):
        found.append({"agent": a.name, "agents": [a.name], "rank": rank, "what": what, "layer": layer, "fix": fix})

    keys: dict[str, list[str]] = {}
    for a in agents:
        for k in a.keys:
            keys.setdefault(k, []).append(a.name)
    for a in agents:
        reach = _reach(a, by)
        leaves = [(d, p) for d, p in reach if not a.ratified and not any(by[x.casefold()].ratified for x in p)]
        gaps = [f"it may {' or '.join(a.acts)} by itself"] if a.acts and not a.ratified else []
        if leaves:
            d, p = leaves[0]
            gaps.append(f"its work leaves for {d}" + (f" through {' then '.join(p)}" if p else ""))
        if gaps:
            add(a, 1, " and ".join(gaps) + ", and nobody ratifies first", "prospective review",
                "add a ratifies: line with the person who checks its work before it acts or sends, or let it only "
                "draft and keep its work on this machine")
        if private is not None and reach and a.reads:
            hit = [r for r in a.reads if private.kinds(r)]
            if hit:
                add(a, 1, f"it reads {'; '.join(hit)}, which is private, and its work leaves for {reach[0][0]}",
                    "stewardship register", "keep that data from it, or keep its work on this machine")
        if a.origin == "your file" and a.owner.strip().lower() in NOBODY:
            add(a, 2, "nobody is written as answering for it", "accountability chain", "add an owner: line with the person who answers for it")
        if (a.acts or reach) and not a.stop.strip():
            add(a, 2, "it acts or sends outside, and nobody wrote how to stop it", "override protocol",
                "add a stop: line that says how to stop it, and try it once")
        last = _date(a.last_run)
        if a.keys and last and (today - last).days > quiet_days:
            add(a, 2, f"it last ran on {last.isoformat()}, {(today - last).days} days ago, and still holds "
                      f"{', '.join(a.keys)}", "stewardship register", "retire it and revoke its keys, or say why it stays")
        for nxt in a.passes:
            if nxt.casefold() not in by:
                add(a, 3, f"it passes work to '{nxt}', which has no record here", "inter-agent council",
                    f"add a record for {nxt}")
    for k, names in keys.items():
        if len(names) > 1:
            found.append({"agent": " and ".join(names), "agents": names, "rank": 3, "what": f"they share one key, {k}, so revoking it "
                          "for one stops all of them", "layer": "stewardship register",
                          "fix": "give each agent its own key"})
    found.sort(key=lambda f: f["rank"])
    return found


def _show(v) -> str:
    if isinstance(v, list):
        return "; ".join(v) if v else NOT_WRITTEN
    return v or NOT_WRITTEN


def _needs(found: list[dict]) -> str:
    n = len({x for f in found for x in f["agents"]})
    return f"{n} need{'s' if n == 1 else ''} a look." if n else "None needs a look."


def register_md(agents: list[Agent], found: list[dict], today: date, path: str = DEFAULT_PATH) -> str:
    mine = [a for a in agents if a.origin == "your file"]
    L = ["# Your agents", "",
         f"{len(agents)} agent{'s' if len(agents) != 1 else ''}: {len(mine)} from {path}, "
         f"{len(agents) - len(mine)} from kb's models file. "
         + _needs(found), ""]
    if not mine:
        L += [f"Your own agents are not written yet. Make the file with: kb agents init, then fill in {path}.", ""]
    if found:
        L += ["## Needs a look", ""]
        for i, f in enumerate(found, 1):
            L += [f"{i}. {f['agent']}: {f['what']}.", f"   Fix: {f['fix']}. ({f['layer']})"]
        L.append("")
    L += ["## The register", ""]
    for a in agents:
        at = f" ({a.where})" if a.where else ""
        last = _date(a.last_run)
        ago = f" ({(today - last).days} days ago)" if last else ""
        L += [f"### {a.name}{at}", f"does: {_show(a.does)}",
              f"reads: {_show(a.reads)} · sends: {_show(a.sends)}",
              f"may: {_show(a.may)} · ratifies: {_show(a.ratifies)} · owner: {_show(a.owner)}",
              f"stop: {_show(a.stop)} · keys: {_show(a.keys)}"
              + (f" · passes: {'; '.join(a.passes)}" if a.passes else ""),
              f"last run: {_show(a.last_run)}{ago}", ""]
    L.append("kb reads what was written here. It does not inspect the agents, so a record is only as true as its writer.")
    return "\n".join(L)


def as_json(agents: list[Agent], found: list[dict]) -> dict:
    return {"agents": [asdict(a) | {"where": a.where, "acts": a.acts, "ratified": a.ratified} for a in agents],
            "needs_a_look": found}


def init(path: str | Path, force: bool = False) -> Path:
    p = Path(path)
    if p.exists() and not force:
        raise KeyError(f"{p} is there already. It is yours: edit it, or add --force to start it again.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(TEMPLATE, encoding="utf-8")
    return p
