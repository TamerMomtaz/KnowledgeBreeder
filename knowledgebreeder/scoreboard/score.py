"""Score a plant graph against a hand-checked gold file.

The gold format is the seed's (see seed/pid-to-kg/scripts/eval_kg.py), so one
gold file serves both tools:

    {"tags": ["TK-101", ...],
     "feeds": [["TK-101", "P-101"], ...],          equipment-level flow
     "loops": {"F-0502": ["FE-0502", "FIT-0502"]}}

Reports precision, recall and F1 for tags and for flow, and loop recall with
member overlap. ``flow`` is the number that matters most: connections are
where every published method is weakest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..graph import PlantGraph, _norm


def prf(pred: set, gold: set) -> dict:
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "missing": sorted(map(str, gold - pred)), "extra": sorted(map(str, pred - gold))}


def score(pg: PlantGraph, gold: dict) -> dict:
    pred_tags = {_norm(d["tag"]) for _n, d in pg.g.nodes(data=True)
                 if d.get("tag") and d.get("type") in ("Equipment", "Instrument", "Component")}
    res = {"tags": prf(pred_tags, {_norm(t) for t in gold.get("tags", [])})}
    feeds = pg.feeds()
    pred_feeds = {(_norm(pg.label(u)), _norm(pg.label(v))) for u, v in feeds.edges}
    res["flow"] = prf(pred_feeds, {(_norm(a), _norm(b)) for a, b in gold.get("feeds", [])})
    found, overlaps = 0, []
    loops = {_norm(pg.label(l).removeprefix("LOOP:").split("@")[0]): l for l in pg.of_type("ControlLoop")}
    for key, members in gold.get("loops", {}).items():
        lid = loops.get(_norm(key))
        if lid is None:
            continue
        found += 1
        pm = {_norm(pg.label(m)) for m, _r in pg.loop_members(lid)}
        gm = {_norm(m) for m in members}
        overlaps.append(len(pm & gm) / len(pm | gm) if pm | gm else 1.0)
    n = len(gold.get("loops", {}))
    res["loops"] = {"recall": round(found / n, 3) if n else None,
                    "member_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else None}
    return res


def headline(res: dict) -> dict:
    return {"tags_f1": res["tags"]["f1"], "flow_f1": res["flow"]["f1"], "loop_recall": res["loops"]["recall"]}


def log(res: dict, ledger: str | Path, label: str, note: str = "") -> dict:
    """Append one line to the ledger, so scores over time stay visible."""
    row = {"when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": label, "note": note, **headline(res)}
    p = Path(ledger)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def beats(challenger: dict, champion: dict, tolerance: float = 0.005) -> tuple[bool, str]:
    """The promotion rule: flow F1 must rise, and nothing else may fall."""
    c, k = headline(challenger), headline(champion)
    for m in ("tags_f1", "loop_recall"):
        if c[m] is not None and k[m] is not None and c[m] < k[m] - tolerance:
            return False, f"{m} fell from {k[m]} to {c[m]}"
    if c["flow_f1"] <= k["flow_f1"] + tolerance:
        return False, f"flow_f1 did not rise ({k['flow_f1']} -> {c['flow_f1']})"
    return True, f"flow_f1 rose from {k['flow_f1']} to {c['flow_f1']}"
