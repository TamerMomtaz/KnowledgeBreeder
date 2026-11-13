"""kb: the KnowledgeBreeder command line.

    kb read     drawing.pdf --page 3            pipe skeleton from a vector page (JSON)
    kb stats    work/plant/kg                   measure the plant and the graph
    kb describe work/plant/kg                   plant description, source to sink
    kb brief    work/plant/kg P-101             everything about one item
    kb whatif   work/plant/kg fail P-101        what loses supply if it stops
    kb whatif   work/plant/kg isolate P-101     valves to close around it
    kb whatif   work/plant/kg spof              single points of failure, ranked
    kb research work/plant/kg                   questions worth checking
    kb score    work/plant/kg gold.json         score against a checked gold file

    kb log runs                                 recent runs, with cost and scores
    kb log show RUN                             one run, step by step
    kb log workers --score flow_f1              leaderboard of readers and models
    kb log compare RUN_A RUN_B                  what got better or worse, and where
    kb log start / step / end                   record work done outside kb (a model call, a person)

The graph argument is a graph.json, or the folder holding one.
The run log is one SQLite file: --db PATH, or the KB_RUNLOG variable, or runs.db here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read"); r.add_argument("pdf"); r.add_argument("--page", type=int, default=1)
    r.add_argument("--reader", default="vector_geometry"); r.add_argument("--rotation", type=int, default=0)
    r.add_argument("--out")
    r.add_argument("--runlog", help="record this read in a run log (SQLite file)")
    r.add_argument("--run", help="add the step to this run instead of starting a new one")
    for name in ("stats", "describe", "research"):
        s = sub.add_parser(name); s.add_argument("graph"); s.add_argument("--json", action="store_true")
    b = sub.add_parser("brief"); b.add_argument("graph"); b.add_argument("tag")
    w = sub.add_parser("whatif"); w.add_argument("graph"); w.add_argument("action", choices=["fail", "isolate", "spof"])
    w.add_argument("tag", nargs="?")
    sc = sub.add_parser("score"); sc.add_argument("graph"); sc.add_argument("gold")
    sc.add_argument("--log", help="append the headline numbers to this ledger (JSON lines)")
    sc.add_argument("--label", default="run"); sc.add_argument("--note", default="")
    sc.add_argument("--runlog", help="record the scores in a run log (SQLite file)")
    sc.add_argument("--run", help="add the step to this run instead of starting a new one")
    sc.add_argument("--worker", help="what produced the graph, e.g. the reader or pipeline name")
    sc.add_argument("--version"); sc.add_argument("--subject", help="what was scored, e.g. the sheet")
    lg = sub.add_parser("log", help="the run log")
    lg.add_argument("--db", default=os.environ.get("KB_RUNLOG", "runs.db"))
    ls = lg.add_subparsers(dest="log_cmd", required=True)
    x = ls.add_parser("runs"); x.add_argument("--task"); x.add_argument("--limit", type=int, default=20)
    x = ls.add_parser("show"); x.add_argument("run"); x.add_argument("--payloads", action="store_true")
    x = ls.add_parser("workers"); x.add_argument("--task"); x.add_argument("--score")
    x = ls.add_parser("compare"); x.add_argument("base"); x.add_argument("challenger")
    ls.add_parser("failures")
    x = ls.add_parser("export"); x.add_argument("run", nargs="?"); x.add_argument("--out")
    x = ls.add_parser("start"); x.add_argument("--task", required=True); x.add_argument("--label"); x.add_argument("--subject")
    x = ls.add_parser("end"); x.add_argument("run"); x.add_argument("--status", default="ok"); x.add_argument("--error")
    x.add_argument("--score", action="append", default=[], metavar="NAME=VALUE")
    x = ls.add_parser("step"); x.add_argument("run"); x.add_argument("--name", required=True)
    x.add_argument("--worker"); x.add_argument("--version"); x.add_argument("--subject")
    x.add_argument("--ms", type=float); x.add_argument("--tokens-in", type=int); x.add_argument("--tokens-out", type=int)
    x.add_argument("--cost", type=float); x.add_argument("--status", default="ok"); x.add_argument("--error")
    x.add_argument("--input-file"); x.add_argument("--output-file")
    x.add_argument("--score", action="append", default=[], metavar="NAME=VALUE")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    def dump(x):
        print(json.dumps(x, indent=1, ensure_ascii=False))

    if a.cmd == "read":
        from .readers import get
        reader = get(a.reader)
        if a.runlog:
            from .runlog import RunLog
            log = RunLog(a.runlog)
            run = log.get(a.run) if a.run else log.start("read", label=a.reader, subject=os.path.basename(a.pdf))
            try:
                with run.step("read", worker=reader.name, version=reader.version, subject=f"page_{a.page:02d}",
                              input={"pdf": a.pdf, "page": a.page, "rotation": a.rotation}) as st:
                    res = reader.read(a.pdf, a.page, a.rotation).to_dict()
                    st.output = {"stats": res["stats"], "warnings": res["warnings"]}
            except BaseException as e:
                if not a.run:
                    run.end("failed", error=f"{type(e).__name__}: {e}")
                raise
            if not a.run:
                run.end()
            print(f"run log: {run.id}", file=sys.stderr)
        else:
            res = reader.read(a.pdf, a.page, a.rotation).to_dict()
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=1)
            print(f"{a.out}: {res['stats']}")
            for wmsg in res["warnings"]:
                print("warning:", wmsg)
        else:
            dump(res)
        return 0

    if a.cmd == "log":
        return _log(a, dump)

    from .graph import PlantGraph
    from .use import manipulation, research, statistics, synthesis
    pg = PlantGraph.load(a.graph)
    try:
        if a.cmd == "stats":
            s = statistics.stats(pg)
            dump(s) if a.json else print(statistics.to_markdown(s))
        elif a.cmd == "describe":
            print(synthesis.describe(pg))
        elif a.cmd == "research":
            q = research.questions(pg)
            dump(q) if a.json else print(research.to_markdown(q))
        elif a.cmd == "brief":
            print(synthesis.brief(pg, a.tag))
        elif a.cmd == "whatif":
            if a.action == "spof":
                dump(manipulation.single_points(pg))
            elif not a.tag:
                ap.error(f"whatif {a.action} needs a tag")
            else:
                dump(getattr(manipulation, a.action)(pg, a.tag))
        elif a.cmd == "score":
            from .scoreboard import score as sb
            t0 = time.perf_counter()
            with open(a.gold, encoding="utf-8") as f:
                res = sb.score(pg, json.load(f))
            dump(res)
            if a.runlog:
                from .runlog import RunLog
                log = RunLog(a.runlog)
                run = log.get(a.run) if a.run else log.start("score", label=a.label, subject=a.subject or a.graph)
                head = {k: v for k, v in sb.headline(res).items() if v is not None}
                run.record("score", worker=a.worker or a.label, version=a.version, subject=a.subject or a.graph,
                           input={"graph": a.graph, "gold": a.gold}, output=res, scores=head,
                           duration_ms=round((time.perf_counter() - t0) * 1000, 3))
                if not a.run:
                    for k, v in head.items():
                        run.score(k, v)
                    run.end()
                print(f"run log: {run.id}", file=sys.stderr)
            if a.log:
                print("logged:", sb.log(res, a.log, a.label, a.note))
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2
    return 0


def _pairs(items: list[str]) -> dict[str, float]:
    out = {}
    for it in items:
        k, sep, v = it.partition("=")
        if not sep:
            raise SystemExit(f"--score wants NAME=VALUE, got '{it}'")
        out[k] = float(v)
    return out


def _load(path: str | None):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except ValueError:
        return text


def _log(a, dump) -> int:
    from .runlog import RunLog, query
    if a.log_cmd not in ("start",) and not os.path.exists(a.db):
        print(f"error: no run log at {a.db} (use --db PATH or set KB_RUNLOG)", file=sys.stderr)
        return 2
    log = RunLog(a.db)
    try:
        if a.log_cmd == "runs":
            dump(query.runs(log, a.task, a.limit))
        elif a.log_cmd == "show":
            dump(query.show(log, a.run, a.payloads))
        elif a.log_cmd == "workers":
            dump(query.workers(log, a.task, a.score))
        elif a.log_cmd == "compare":
            dump(query.compare(log, a.base, a.challenger))
        elif a.log_cmd == "failures":
            dump(query.failures(log))
        elif a.log_cmd == "export":
            rows = query.export(log, a.run)
            if a.out:
                with open(a.out, "w", encoding="utf-8") as f:
                    f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
                print(f"{a.out}: {len(rows)} records")
            else:
                for r in rows:
                    print(json.dumps(r, ensure_ascii=False))
        elif a.log_cmd == "start":
            print(log.start(a.task, a.label, a.subject).id)
        elif a.log_cmd == "end":
            run = log.get(a.run)
            for k, v in _pairs(a.score).items():
                run.score(k, v)
            run.end(a.status, a.error)
        elif a.log_cmd == "step":
            print(log.get(a.run).record(
                a.name, worker=a.worker, version=a.version, subject=a.subject, duration_ms=a.ms,
                tokens_in=a.tokens_in, tokens_out=a.tokens_out, cost=a.cost, status=a.status, error=a.error,
                input=_load(a.input_file), output=_load(a.output_file), scores=_pairs(a.score)))
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
