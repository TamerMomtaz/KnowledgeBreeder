"""Your verdict on an advice run: the pieces you would act on, and whose answer you picked.

The command line and kb serve both write through here, so the rules are the same wherever you tick: one rating
per answer, one pick per run, numbers that exist, and nothing recorded twice.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..runlog import RunLog, Step, query


def pieces_from_words(words: Sequence[str]) -> list[int]:
    """'1 6', '1,6' or 'none' as a list of piece numbers. An empty list means none."""
    if [w.lower() for w in words] == ["none"]:
        return []
    try:
        return sorted({int(x) for w in words for x in w.replace(",", " ").split()})
    except ValueError:
        raise KeyError("give the numbers of the pieces you would act on, as 1 6, or the word none.") from None


def rate(log: RunLog, run_id: str, act: Sequence[int], worker: str | None = None, why: str | None = None) -> dict:
    """Store the share of one answer's pieces you would act on, as the score would_act."""
    run = log.get(run_id)
    shown = query.show(log, run.id, payloads=True)
    if shown["task"] != "advise":
        raise KeyError(f"{run.id} is a {shown['task']} run, not advice.")
    steps = [s for s in shown["steps"] if s["name"] == "advise" and s["status"] == "ok" and s["worker"]]
    names = [s["worker"] for s in steps]
    if worker:
        steps = [s for s in steps if s["worker"] == worker]
    if not names:
        raise KeyError(f"nobody answered in {run.id}, so there is nothing to rate.")
    if worker and not steps:
        raise KeyError(f"'{worker}' gave no answer in {run.id}. Those that did: {', '.join(names)}.")
    if len(steps) > 1:
        raise KeyError(f"{run.id} holds several answers. Say whose with --worker NAME: {', '.join(names)}.")
    s = steps[0]
    advice = s["output"].get("advice") if isinstance(s["output"], dict) else None
    if not advice:
        raise KeyError(f"{s['worker']} showed no advice in {run.id}, so there is nothing to rate.")
    if "would_act" in s["scores"]:
        raise KeyError(f"a rating is already recorded for {s['worker']} in {run.id}.")
    n, act = len(advice), sorted(set(act))
    if act and (act[0] < 1 or act[-1] > n):
        raise KeyError(f"{s['worker']} showed {n} pieces in {run.id}, numbered 1 to {n}.")
    why = " ".join((why or "").split())
    note = f"would act on {', '.join(map(str, act)) or 'none'} of {n}" + (f". Why: {why}" if why else "")
    Step(run, s["id"]).score("would_act", len(act) / n, note=note)
    return {"run": run.id, "worker": s["worker"], "act": act, "n": n, "share": len(act) / n}


def pick(log: RunLog, run_id: str, name: str) -> dict:
    """Record whose answer you chose: 1 for that model, 0 for every other that answered."""
    run = log.get(run_id)
    steps = [s for s in query.show(log, run.id)["steps"] if s["worker"] and s["status"] == "ok"]
    names = [s["worker"] for s in steps]
    if name not in names:
        raise KeyError(f"'{name}' gave no answer in {run.id}. Those that did: {', '.join(names) or 'none'}.")
    if any("picked" in s["scores"] for s in steps):
        raise KeyError(f"a pick is already recorded for {run.id}.")
    for s in steps:
        Step(run, s["id"]).score("picked", 1.0 if s["worker"] == name else 0.0, note="chosen by a person")
    return {"run": run.id, "picked": name, "over": [n for n in names if n != name]}
