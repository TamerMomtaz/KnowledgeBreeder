"""The picture: one person's cards in one local file, and the names that tie them together."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import cards as cardmod

VERSION = 1
STOP = frozenset("""a an the of and or for to in on at by with from my his her its it is are was were be been that this
these those as all any every each not no one into per so than then can same both also other them they their what which
who how where when there here has have had do does did already more most only just own up out if but we you he she
i me our your will would should could may might about over under after before between still yet very much many some
such via vs etc""".split())
_WORD = re.compile(r"[^\W_]+(?:[-→'’][^\W_]+)*", re.UNICODE)
_COLLECTIVE = re.compile(r"^(all|every|any|each|everything|the whole)\b", re.I)


def stem(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def words(text: str) -> list[str]:
    """Content words of a text: lower case, plural s dropped, small words removed."""
    return [s for w in _WORD.findall(text or "") if len(w) > 1 and w.lower() not in STOP and (s := stem(w)) not in STOP]


def _norm(text: str) -> str:
    return " ".join(w.lower() for w in _WORD.findall(text or ""))


def _name_parts(name: str) -> list[str]:
    """'Dar, "The Oven"' -> Dar, The Oven. 'Recipe cards (bread and cake)' -> Recipe cards, bread, cake."""
    out = [name]
    outside = re.sub(r"\([^)]*\)", " ", name)
    out += re.split(r"\s*,\s*", outside)
    for inner in re.findall(r"\(([^)]*)\)", name):
        out += re.split(r"\s*,\s*|\s+and\s+", inner)
    out += re.findall(r"[\"“]([^\"”]+)[\"”]", name)
    seen, parts = set(), []
    for p in out:
        n = re.sub(r"^the\s+", "", _norm(p))
        if len(n) >= 3 and n not in seen:
            seen.add(n)
            parts.append(n)
    return parts


class Picture:
    """Cards keyed by id, plus areas the person has named that hold no card yet."""

    def __init__(self, cards: dict[str, dict] | None = None, areas: list[str] | None = None):
        self.cards: dict[str, dict] = cards or {}
        self.areas: list[str] = areas or []
        self._index = None

    # ---- file ---------------------------------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Picture":
        """A picture.json, or a cards file read on the spot."""
        p = Path(path)
        if not p.exists():
            raise KeyError(f"no picture at {p}. Make one with: kb picture add CARDS.md --to {p}")
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            data = json.loads(text)
            return cls({c["id"]: c for c in data.get("cards", [])}, list(data.get("areas", [])))
        pic = cls()
        pic.add(cardmod.parse(text, origin=p.name))
        return pic

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": VERSION, "areas": self.areas, "cards": list(self.cards.values())}
        p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    def add(self, cards: list[dict]) -> dict:
        """Merge cards in. A card with a name already held replaces the older one."""
        added, updated = [], []
        for c in cards:
            (updated if c["id"] in self.cards else added).append(c["name"])
            self.cards[c["id"]] = c
        self._index = None
        return {"added": added, "updated": updated}

    def add_area(self, name: str) -> bool:
        if name.strip() and name.strip().lower() not in {a.lower() for a in self.all_areas()}:
            self.areas.append(name.strip())
            return True
        return False

    # ---- reading ------------------------------------------------------------------------------------------
    def name(self, cid: str) -> str:
        return self.cards[cid]["name"]

    def by_area(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = defaultdict(list)
        for c in self.cards.values():
            out[c["area"] or "No area given"].append(c)
        for a in self.areas:
            out.setdefault(a, [])
        return dict(out)

    def all_areas(self) -> list[str]:
        return list(self.by_area())

    def newest(self) -> str | None:
        dates = [c["last_date"] for c in self.cards.values() if c.get("last_date")]
        return max(dates) if dates else None

    # ---- names --------------------------------------------------------------------------------------------
    def _build(self):
        alias_owner: dict[str, set[str]] = defaultdict(set)
        tokens: dict[str, set[str]] = {}
        for cid, c in self.cards.items():
            parts = _name_parts(c["name"]) + [re.sub(r"^the\s+", "", _norm(a)) for a in c.get("aliases", [])]
            for a in parts:
                if a:
                    alias_owner[a].add(cid)
            tokens[cid] = set(words(" ".join(parts)))
        self._index = (alias_owner, tokens)
        return self._index

    def resolve(self, text: str) -> list[str]:
        """Which cards a free-text name points to. Empty when none fits, when two fit equally, or when the
        name is a collective ('all my teaching')."""
        return self._resolve(text)[0]

    def unclear(self, text: str) -> list[str]:
        """Cards that fit a name equally well, when no single one wins. The person has to say which."""
        return self._resolve(text)[1]

    def _resolve(self, text: str) -> tuple[list[str], list[str]]:
        alias_owner, tokens = self._index or self._build()
        if _COLLECTIVE.match(text.strip()):
            return [], []
        exact = alias_owner.get(re.sub(r"^the\s+", "", _norm(text)))
        if exact and len(exact) == 1:
            return list(exact), []
        whole = self._resolve_one(text, alias_owner, tokens)
        pieces = [p for p in re.split(r"\s*,\s*|\s+and\s+|\s*/\s*|\s*;\s*", text) if p.strip()]
        found: list[str] = []                       # 'the order book, the stock sheet and the class' names three cards
        if len(pieces) > 1:
            for piece in pieces:
                hit = self._resolve_one(piece, alias_owner, tokens)
                if len(hit) == 1 and hit[0] not in found:
                    found.append(hit[0])
        if found:
            return found, []
        return (whole, []) if len(whole) == 1 else ([], whole)

    @staticmethod
    def _resolve_one(text: str, alias_owner, tokens) -> list[str]:
        norm = re.sub(r"^the\s+", "", _norm(text))
        if not norm:
            return []
        exact = alias_owner.get(norm)
        if exact and len(exact) == 1:
            return list(exact)
        want = set(words(text))
        if not want:
            return []
        phrase = {cid for a, owners in alias_owner.items() if len(owners) == 1
                  and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(a), norm) for cid in owners}
        best, best_key = [], (0.0, 0)
        for cid, toks in tokens.items():
            cover = len(want & toks) / len(want)
            if cover > 0.5 or (cid in phrase and cover > 0):
                key = (cover, 1 if cid in phrase else 0)
                if key > best_key:
                    best, best_key = [cid], key
                elif key == best_key:
                    best.append(cid)
        return best if len(best) <= 3 else []

    def mentions(self, text: str, skip: str | None = None) -> list[str]:
        """Cards whose own distinct name appears inside a sentence."""
        alias_owner, _ = self._index or self._build()
        norm = _norm(text)
        out = []
        for a, owners in sorted(alias_owner.items(), key=lambda kv: -len(kv[0])):
            if len(owners) == 1 and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(a), norm):
                cid = next(iter(owners))
                if cid != skip and cid not in out:
                    out.append(cid)
        return out

    def links(self) -> list[dict]:
        """Every 'LINKS TO MY OTHER WORK' line, with the cards it points to."""
        out = []
        for cid, c in self.cards.items():
            for f in c["links"]:
                target, how = f[0], " | ".join(f[1:])
                to = [t for t in self.resolve(target) if t != cid]
                out.append({"from": cid, "target": target, "how": how, "to": to,
                            "unclear": [] if to else [t for t in self.unclear(target) if t != cid],
                            "collective": bool(_COLLECTIVE.match(target.strip()))})
        return out

    def degree(self) -> Counter:
        """How many other cards each card is tied to, in either direction."""
        pairs = {tuple(sorted((link["from"], t))) for link in self.links() for t in link["to"]}
        deg: Counter = Counter({cid: 0 for cid in self.cards})
        for a, b in pairs:
            deg[a] += 1
            deg[b] += 1
        return deg

    def idf(self, docs: dict[str, list[str]]) -> dict[str, float]:
        n = max(len(docs), 1)
        df = Counter(w for d in docs.values() for w in set(d))
        return {w: math.log(n / k) for w, k in df.items()}

