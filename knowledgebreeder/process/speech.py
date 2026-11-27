"""Read one person's description of their job, said in plain words, into sentences kb understands.

One file is one person. It starts with a few header lines, then the job in their own words:

    person: Mona
    job: order desk
    also: the desk, orders

    I get the order from the customer.
    I check the order is complete.
    If the order is over 50 boxes, I send it to Karim.
    Otherwise I send it to the kitchen.
    I wait for all of: the bread from the bakery, the filling from the cold room.

kb knows these kinds of sentence, in English and in Arabic:

    get      I get THING from WHO              أستلم THING من WHO
    send     I send / pass / give THING to WHO أرسل / أسلم THING إلى WHO
    wait     I wait for all of / any of / one of: A from X, B from Y
                                               أنتظر كل من / أي من / واحد من: ...
    check    I check / measure / count WHAT    أتحقق من / أراجع / أقيس WHAT
    if       If CONDITION, SENTENCE            إذا CONDITION، SENTENCE
    else     Otherwise SENTENCE                وإلا SENTENCE
    step     anything else: a piece of work done in place

This is pattern matching on words, not understanding. A sentence kb cannot place is kept as a step, word for word,
so nothing the person said is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

JOINS = {"all": "all of", "any": "any of", "one": "one of"}

_HEAD = {
    "person": "person", "name": "person", "الاسم": "person", "الشخص": "person",
    "job": "job", "role": "job", "الوظيفة": "job", "العمل": "job",
    "also": "also", "aliases": "also", "also called": "also", "يسمى أيضا": "also", "أيضا": "also",
}
_JOIN_WORDS = {
    "all of": "all", "both": "all", "كل من": "all", "كل": "all",
    "any of": "any", "either": "any", "أي من": "any", "اي من": "any", "أي": "any",
    "one of": "one", "only one of": "one", "واحد من": "one", "واحدة من": "one",
}
_I = r"(?:i\s+(?:also\s+|then\s+|usually\s+)?|then\s+i\s+|and\s+i\s+|أنا\s+|ثم\s+)?"
_GET = re.compile(_I + r"(?:get|gets|receive|take|collect|pick up|am given|أستلم|استلم|آخذ|اخذ|أتلقى|اتلقى|يصلني)\s+"
                  r"(?P<thing>.+?)\s+(?:from|من)\s+(?P<who>.+)$", re.I)
_SEND = re.compile(_I + r"(?:send|sends|pass|give|hand over|hand|deliver|forward|email|return|أرسل|ارسل|أسلم|اسلم|"
                   r"أعطي|اعطي|أمرر|امرر|أبعت|ابعت|أوصل|اوصل)\s+(?P<thing>.+?)\s+(?:to|إلى|الى)\s+(?P<who>.+)$", re.I)
_WAIT = re.compile(_I + r"(?:wait for|need|أنتظر|انتظر|أحتاج|احتاج)\s+(?P<join>" + "|".join(
    sorted(map(re.escape, _JOIN_WORDS), key=len, reverse=True)) + r")\s*:?\s*(?P<list>.+)$", re.I)
_CHECK = re.compile(_I + r"(?:check|checks|measure|count|weigh|test|inspect|verify|look over|أتحقق من|اتحقق من|"
                    r"أراجع|اراجع|أقيس|اقيس|أعد|اعد|أزن|ازن|أفحص|افحص)\s+(?P<what>.+)$", re.I)
_IF = re.compile(r"(?:if|when|إذا|اذا|لو)\s+(?P<cond>.+?)\s*[,،]\s*(?:then\s+)?(?P<rest>.+)$", re.I)
_ELSE = re.compile(r"(?:otherwise|else|if not|وإلا|والا|غير ذلك)\s*[,،]?\s*(?P<rest>.+)$", re.I)
_TAIL = re.compile(r"\s+(?:for|so|so that|because|when|by|before|after|every|each|لكي|حتى|لأن|عندما|قبل|بعد)\s.*$",
                   re.I)
_SPLIT = re.compile(r"\s*(?:[,;،؛]|\band\b|\bor\b|\s+و\s+|\s+أو\s+)\s*", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")
_PRONOUNS = {"it", "them", "this", "that", "these", "those", "everything", "هو", "هي", "هذا", "هذه", "ذلك", "كله"}
_STOP = {"the", "a", "an", "my", "our", "his", "her", "their", "of", "to", "from", "in", "on", "for", "with", "and",
         "ال", "من", "إلى", "الى", "في", "على"}


@dataclass
class Sentence:
    kind: str                     # get, send, wait, check, if, else, step
    text: str                     # what the person said, word for word
    line: int                     # where in the file
    thing: str = ""
    who: str = ""
    join: str = ""                # all, any, one (wait sentences only)
    items: list[tuple[str, str]] = field(default_factory=list)   # (thing, who) the wait is for; who may be ""
    cond: str = ""                # if sentences: the condition
    then: "Sentence | None" = None  # if / else sentences: what is done


@dataclass
class Person:
    name: str
    job: str = ""
    also: list[str] = field(default_factory=list)
    source: str = ""
    sentences: list[Sentence] = field(default_factory=list)

    def names(self) -> set[str]:
        return {k for k in (norm(self.name), norm(self.job), *(norm(a) for a in self.also)) if k}


def norm(s: str) -> str:
    """A name as kb compares it: lower case, no 'the', no punctuation."""
    s = re.sub(r"[^\w\s]", " ", s.lower())
    words = [w[2:] if w.startswith("ال") and len(w) > 3 else w for w in s.split()]
    return " ".join(w for w in words if w not in {"the", "a", "an", "our", "my", "mr", "ms", "mrs"})


def words(s: str) -> set[str]:
    return {w for w in norm(s).split() if w not in _STOP and len(w) > 1}


def vague(thing: str) -> bool:
    """'it', 'them': a thing that names nothing, so it matches whatever the other side says."""
    return not words(thing) or norm(thing) in _PRONOUNS


def _clean(s: str) -> str:
    return s.strip().strip(".!?؟").strip()


def _who(s: str) -> str:
    return _clean(_TAIL.sub("", _clean(s)))


def parse_sentence(text: str, line: int = 0) -> Sentence:
    t = _clean(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text))
    m = _ELSE.match(t)
    if m:
        return Sentence("else", t, line, then=parse_sentence(m["rest"], line))
    m = _IF.match(t)
    if m:
        return Sentence("if", t, line, cond=_clean(m["cond"]), then=parse_sentence(m["rest"], line))
    m = _WAIT.match(t)
    if m:
        items = []
        for part in _SPLIT.split(m["list"]):
            part = _clean(part)
            if not part:
                continue
            g = re.match(r"(?P<thing>.+?)\s+(?:from|من)\s+(?P<who>.+)$", part, re.I)
            items.append((_clean(g["thing"]), _who(g["who"])) if g else (part, ""))
        return Sentence("wait", t, line, join=_JOIN_WORDS[m["join"].lower()], items=items)
    m = _GET.match(t)
    if m:
        return Sentence("get", t, line, thing=_clean(m["thing"]), who=_who(m["who"]))
    m = _SEND.match(t)
    if m:
        return Sentence("send", t, line, thing=_clean(m["thing"]), who=_who(m["who"]))
    m = _CHECK.match(t)
    if m:
        return Sentence("check", t, line, thing=_clean(m["what"]))
    return Sentence("step", t, line)


def read_text(text: str, name: str = "", source: str = "") -> Person:
    p = Person(name=name, source=source)
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        h = re.match(r"([^:：]{1,20})\s*[:：]\s*(.+)$", line)
        if h and h[1].strip().lower() in _HEAD:
            key, val = _HEAD[h[1].strip().lower()], h[2].strip()
            if key == "person":
                p.name = val
            elif key == "job":
                p.job = val
            else:
                p.also += [a.strip() for a in re.split(r"[,،;]", val) if a.strip()]
            continue
        for piece in _SENTENCE_END.split(line):
            if _clean(piece):
                p.sentences.append(parse_sentence(piece, i))
    if not p.name:
        p.name = p.job or "someone"
    return p


def read_file(path: str | Path) -> Person:
    path = Path(path)
    return read_text(path.read_text(encoding="utf-8"), name=path.stem, source=str(path))


def read_all(paths: list[str | Path]) -> list[Person]:
    """Every .txt and .md file named, or found in the folders named, one person each, in name order."""
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in {".txt", ".md"})
        elif p.exists():
            files.append(p)
        else:
            raise FileNotFoundError(f"no file or folder at {p}")
    return [read_file(f) for f in files]
