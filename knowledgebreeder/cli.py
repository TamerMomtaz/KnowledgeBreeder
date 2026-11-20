"""kb: the KnowledgeBreeder command line.

    kb read     drawing.pdf --page 3            pipe skeleton from a vector page (JSON)
    kb stats    work/plant/kg                   measure the plant and the graph
    kb describe work/plant/kg                   plant description, source to sink
    kb brief    work/plant/kg P-101             everything about one item
    kb whatif   work/plant/kg fail P-101        what loses supply if it stops
    kb whatif   work/plant/kg isolate P-101     valves to close around it
    kb whatif   work/plant/kg spof              single points of failure, ranked
    kb research work/plant/kg                   questions worth checking
    kb walk     work/plant/kg --out work/plant.html   the plant as one page, what-if on click, opens offline
    kb score    work/plant/kg gold.json         score against a checked gold file

    kb log runs                                 recent runs, with cost and scores
    kb log show RUN                             one run, step by step
    kb log workers --score flow_f1              leaderboard of readers and models
    kb log compare RUN_A RUN_B                  what got better or worse, and where
    kb log start / step / end                   record work done outside kb (a model call, a person)

    kb picture add cards.md                     merge project cards into your picture
    kb picture show                             how many cards, in which areas
    kb picture overlaps / gaps / reuse          the same idea twice, what is missing, what could travel
    kb picture brief                            a short list of moves worth a look
    kb picture town --out work/town.html        the picture as a town, one file, opens offline

The graph argument is a graph.json, or the folder holding one.
The run log is one SQLite file: --db PATH, or the KB_RUNLOG variable, or runs.db here.
The picture is one private JSON file: --file PATH, or the KB_PICTURE variable, or work/picture.json here.
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
    wk = sub.add_parser("walk"); wk.add_argument("graph"); wk.add_argument("--out", default="work/plant.html")
    wk.add_argument("--title"); wk.add_argument("--lang", choices=["en", "ar"], default="en")
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
    pc = sub.add_parser("picture", help="the whole picture: one person's projects as one graph")
    pc.add_argument("--file", default=os.environ.get("KB_PICTURE", "work/picture.json"),
                    help="the picture (a picture.json, or a cards file to read on the spot)")
    ps = pc.add_subparsers(dest="pic_cmd", required=True)
    x = ps.add_parser("add"); x.add_argument("cards", nargs="*", help="files holding PROJECT CARDs")
    x.add_argument("--area", action="append", default=[], help="name an area that has no card yet")
    ps.add_parser("show")
    for name in ("overlaps", "gaps", "reuse", "brief"):
        x = ps.add_parser(name); x.add_argument("--json", action="store_true")
        if name in ("gaps", "brief"):
            x.add_argument("--today", help="the date to count from (YYYY-MM-DD), default today")
        if name == "gaps":
            x.add_argument("--quiet-days", type=int, default=90)
    x = ps.add_parser("town"); x.add_argument("--out", default="work/town.html"); x.add_argument("--title")
    x.add_argument("--lang", choices=["en", "ar"], default="en"); x.add_argument("--today")
    x.add_argument("--quiet-days", type=int, default=90)
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
    if a.cmd == "picture":
        try:
            return _picture(a, dump)
        except KeyError as e:
            print(f"error: {e.args[0]}", file=sys.stderr)
            return 2

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
        elif a.cmd == "walk":
            from . import walk
            path = walk.write(pg, a.out, title=a.title, lang=a.lang)
            print(f"{path}: {len(pg.of_type('Equipment', 'Component', 'Instrument', 'Boundary'))} items. "
                  "Open it in a browser. It is private: it holds your plant.")
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


def _picture(a, dump) -> int:
    from datetime import date
    from .picture import Picture, cards, reports
    if a.pic_cmd == "add":
        if not a.cards and not a.area:
            raise KeyError("give at least one cards file, or --area NAME")
        pic = Picture.load(a.file) if os.path.exists(a.file) else Picture()
        out = {"added": [], "updated": [], "areas_added": [], "no_cards_in": []}
        for path in a.cards:
            found = cards.parse_file(path)
            if not found:
                out["no_cards_in"].append(path)
            res = pic.add(found)
            out["added"] += res["added"]; out["updated"] += res["updated"]
        out["areas_added"] = [n for n in a.area if pic.add_area(n)]
        if not a.file.lower().endswith(".json"):
            raise KeyError(f"--file must be a .json file to save into, got {a.file}")
        out["saved"] = str(pic.save(a.file)); out["cards"] = len(pic.cards)
        dump(out)
        return 0
    pic = Picture.load(a.file)
    today = date.fromisoformat(a.today) if getattr(a, "today", None) else None
    if a.pic_cmd == "show":
        dump(reports.summary(pic))
    elif a.pic_cmd == "overlaps":
        o = reports.overlaps(pic)
        dump(o) if a.json else print(reports.overlaps_md(o))
    elif a.pic_cmd == "gaps":
        g = reports.gaps(pic, today, a.quiet_days)
        dump(g) if a.json else print(reports.gaps_md(g))
    elif a.pic_cmd == "reuse":
        r = reports.reuse(pic)
        dump(r) if a.json else print(reports.reuse_md(r))
    elif a.pic_cmd == "brief":
        b = reports.brief(pic, today)
        dump(b) if a.json else print(reports.brief_md(b))
    elif a.pic_cmd == "town":
        from .picture import town
        path = town.write(pic, a.out, today=today, title=a.title, lang=a.lang, quiet_days=a.quiet_days)
        print(f"{path}: {len(pic.cards)} projects in {len(pic.by_area())} areas. Open it in a browser. It is private: it holds your picture.")
    return 0


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
