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
    kb picture advise                           advice written by a model, held to your own cards and your lessons
    kb picture lesson "Quiet is not dead."      teach every later run one rule, in your own words
    kb picture rate RUN 1 6                     mark the pieces you would act on; the share is kb's score

    kb models init / list / check               which models kb may ask, and where each one lives
    kb models pick RUN NAME                     record which model's answer you chose
    kb scout read work/sources                  read saved pages against your projects, look for chances
    kb scout log                                everything the scout read, with what it passed over and why

The graph argument is a graph.json, or the folder holding one.
The run log is one SQLite file: --db PATH, or the KB_RUNLOG variable, or runs.db here.
The picture is one private JSON file: --file PATH, or the KB_PICTURE variable, or work/picture.json here.
The models file is private too: --models-file PATH, or the KB_MODELS variable, or work/models.json here.
Your lessons are one private Markdown file: --lessons PATH, or the KB_LESSONS variable, or work/lessons.md here.
A model on this machine is asked freely. Any other needs --allow NAME, for that one run.
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
    mfile = os.environ.get("KB_MODELS", "work/models.json")
    runlog = os.environ.get("KB_RUNLOG", "runs.db")

    def asking(x):
        x.add_argument("--models-file", default=mfile, help="the models file")
        x.add_argument("--allow", action="append", default=[], metavar="NAME",
                       help="let this run send to a model that is not on this machine")
        x.add_argument("--today", help="the date to count from (YYYY-MM-DD), default today")
        x.add_argument("--json", action="store_true")
        x.add_argument("--runlog", default=runlog, help="record the run in this run log")
        x.add_argument("--no-log", action="store_true", help="do not record the run")

    x = ps.add_parser("advise"); asking(x)
    x.add_argument("--model", help="which model writes the advice, default the file's default")
    x.add_argument("--models", help="several, as a,b,c: each writes its own, and the run log holds them side by side")
    x.add_argument("--project", help="advise on this one project instead of the whole picture")
    x.add_argument("--top", type=int, default=7); x.add_argument("--lang", choices=["en", "ar"], default="en")
    x.add_argument("--show-prompt", action="store_true", help="print what would be sent, and send nothing")
    lfile = os.environ.get("KB_LESSONS", "work/lessons.md")
    x.add_argument("--lessons", default=lfile, help="your lessons file, which every run follows")
    x.add_argument("--no-lessons", action="store_true", help="leave your lessons out of this run, to compare")
    x = ps.add_parser("lesson", help="add one lesson, or list them")
    x.add_argument("text", nargs="*", help="the lesson, in your own words; none lists the lessons")
    x.add_argument("--lessons", default=lfile); x.add_argument("--today")
    x = ps.add_parser("rate", help="mark which pieces of a run's advice you would act on")
    x.add_argument("run"); x.add_argument("pieces", nargs="+", help="the numbers of the pieces you would act on, or: none")
    x.add_argument("--worker", help="whose answer, when the run holds several")
    x.add_argument("--why", help="a short reason, kept with the rating")
    x.add_argument("--runlog", default=runlog)
    md = sub.add_parser("models", help="the models kb may ask, and the gate")
    md.add_argument("--file", default=mfile)
    ms = md.add_subparsers(dest="mod_cmd", required=True)
    x = ms.add_parser("init"); x.add_argument("--url", default=None); x.add_argument("--force", action="store_true")
    ms.add_parser("list")
    x = ms.add_parser("check"); x.add_argument("name", nargs="?")
    x.add_argument("--allow", action="append", default=[], metavar="NAME")
    x = ms.add_parser("pick"); x.add_argument("run"); x.add_argument("name"); x.add_argument("--db", default=runlog)
    so = sub.add_parser("scout", help="read saved sources against your picture")
    so.add_argument("--file", default=os.environ.get("KB_PICTURE", "work/picture.json"), help="the picture")
    so.add_argument("--ledger", default=os.environ.get("KB_SCOUT", "work/scout.jsonl"))
    ss = so.add_subparsers(dest="scout_cmd", required=True)
    x = ss.add_parser("read"); asking(x); x.add_argument("paths", nargs="+", help="saved files, or folders of them")
    x.add_argument("--model"); x.add_argument("--again", action="store_true", help="ask again about sources read before")
    x = ss.add_parser("log"); x.add_argument("--today"); x.add_argument("--json", action="store_true")
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
    if a.cmd in ("picture", "models", "scout"):
        from .models import ModelError, Refused
        try:
            return {"picture": _picture, "models": _models, "scout": _scout}[a.cmd](a, dump)
        except KeyError as e:
            print(f"error: {e.args[0]}", file=sys.stderr)
            return 2
        except Refused as e:                                # the gate: nothing left this machine
            print(str(e), file=sys.stderr)
            return 3
        except ModelError as e:
            print(f"error: {e}", file=sys.stderr)
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
    if a.pic_cmd == "lesson":
        return _lesson(a)
    if a.pic_cmd == "rate":
        return _rate(a)
    pic = Picture.load(a.file)
    today = date.fromisoformat(a.today) if getattr(a, "today", None) else None
    if a.pic_cmd == "advise":
        return _advise(a, dump, pic, today)
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


def _open_log(a, task: str, label: str, subject: str):
    """(log, run) for a command that asks a model, or (None, None) with --no-log."""
    if a.no_log:
        return None, None
    from .runlog import RunLog
    log = RunLog(a.runlog)
    return log, log.start(task, label=label, subject=subject)


def _advise(a, dump, pic, today) -> int:
    from datetime import date
    from . import models
    from .picture import advise as adv
    today = today or date.today()
    book = models.load(a.models_file)
    chosen = book.pick(a.models or a.model)
    project = None
    if a.project:
        found = pic.resolve(a.project)
        if len(found) != 1:
            raise KeyError(f"'{a.project}' does not name one project. The picture holds: "
                           f"{', '.join(c['name'] for c in pic.cards.values())}.")
        project = found[0]
    if not pic.cards:
        raise KeyError("the picture holds no cards yet. Add some with: kb picture add CARDS.md")
    from .picture import lessons as les
    taught, old = ([], 0) if a.no_lessons else les.fit(les.read(a.lessons))
    plans = []
    for m in chosen:                                        # every destination is checked before anything is sent
        lines, left = adv.evidence(pic, m.budget, today, project)
        system, user = adv.prompt(lines, left, today, a.top, a.lang, pic.name(project) if project else None, taught)
        if a.show_prompt:
            host, where = models.place(m.url)
            print(f"--- to {m.name} ({m.model}) at {host}, {where}: {len(system) + len(user):,} characters. "
                  f"Nothing was sent.\n\n{system}\n\n{user}\n")
            continue
        models.gate(m, a.allow, len(system) + len(user), adv.sending(len(lines), len(taught)))
        plans.append(m)
    if a.show_prompt:
        return 0
    log, run = _open_log(a, "advise", ",".join(m.name for m in chosen), pic.name(project) if project else "whole picture")
    results, failed = [], 0
    for m in plans:
        try:
            r = adv.advise(pic, m, allow=a.allow, today=today, top=a.top, lang=a.lang, project=project, lessons=taught)
        except models.ModelError as e:
            failed += 1
            results.append({"worker": m.name, "model": m.model, "error": str(e)})
            if run:
                run.record("advise", worker=m.name, version=m.model, status="failed", error=str(e))
            continue
        results.append(r)
        if run:
            run.record("advise", worker=m.name, version=r["model"], subject=r["project"] or "whole picture",
                       input={"evidence": r["evidence"], "left_out": r["lines_left_out"], "lessons": r["lessons"]},
                       output={"advice": r["advice"], "dropped": r["dropped"], "warnings": r["warnings"]},
                       duration_ms=r["ms"], tokens_in=r["tokens_in"], tokens_out=r["tokens_out"], cost=r["cost"],
                       scores=r["scores"], where=r["where"])
    if run:
        run.end("failed" if failed == len(plans) else "ok")
    if a.json:
        dump({"run": run.id if run else None, "results": results})
    else:
        if old:
            print(f"Note: {old} older lessons in {a.lessons} did not fit and were not sent. Shorten or merge some.\n")
        for r in results:
            print(f"# Advice\n\n{r['worker']} ({r['model']}) gave nothing: {r['error']}" if "error" in r else adv.advice_md(r))
            print()
        if run and len(plans) > 1:
            print(f"Recorded as {run.id} in {a.runlog}. When you have chosen the one you would act on:\n"
                  f"  kb models pick {run.id} NAME\n"
                  f"and mark its pieces you would act on:\n"
                  f"  kb picture rate {run.id} 1 2 --worker NAME")
        elif run:
            print(f"Recorded as {run.id} in {a.runlog}. Mark the pieces you would act on, for example:\n"
                  f"  kb picture rate {run.id} 1 2")
    return 2 if failed == len(plans) else 0


def _lesson(a) -> int:
    from datetime import date

    from .picture import lessons as les
    if not a.text:
        have = les.read(a.lessons)
        print(f"{len(have)} lesson{'' if len(have) == 1 else 's'} in {a.lessons}" + (":\n" + les.numbered(have) if have else
              '. Add one with: kb picture lesson "your rule, in your own words"'))
        return 0
    today = date.fromisoformat(a.today) if a.today else date.today()
    have, new = les.add(a.lessons, " ".join(a.text), today)
    _kept, old = les.fit(have)
    print(("Added. " if new else "That lesson is already there. ") + f"{len(have)} lesson{'' if len(have) == 1 else 's'} "
          f"in {a.lessons}; "
          f"every advice run follows them" + (f", except the {old} oldest, which no longer fit" if old else "") + ".")
    return 0


def _rate(a) -> int:
    from .runlog import RunLog, Step, query
    if not os.path.exists(a.runlog):
        raise KeyError(f"no run log at {a.runlog} (use --runlog PATH or set KB_RUNLOG)")
    log = RunLog(a.runlog)
    run = log.get(a.run)
    shown = query.show(log, run.id, payloads=True)
    if shown["task"] != "advise":
        raise KeyError(f"{run.id} is a {shown['task']} run, not advice.")
    steps = [s for s in shown["steps"] if s["name"] == "advise" and s["status"] == "ok" and s["worker"]]
    names = [s["worker"] for s in steps]
    if a.worker:
        steps = [s for s in steps if s["worker"] == a.worker]
    if not names:
        raise KeyError(f"nobody answered in {run.id}, so there is nothing to rate.")
    if a.worker and not steps:
        raise KeyError(f"'{a.worker}' gave no answer in {run.id}. Those that did: {', '.join(names)}.")
    if len(steps) > 1:
        raise KeyError(f"{run.id} holds several answers. Say whose with --worker NAME: {', '.join(names)}.")
    s = steps[0]
    advice = s["output"].get("advice") if isinstance(s["output"], dict) else None
    if not advice:
        raise KeyError(f"{s['worker']} showed no advice in {run.id}, so there is nothing to rate.")
    if "would_act" in s["scores"]:
        raise KeyError(f"a rating is already recorded for {s['worker']} in {run.id}.")
    n = len(advice)
    if [p.lower() for p in a.pieces] == ["none"]:
        act = []
    else:
        try:
            act = sorted({int(p.strip(",")) for p in a.pieces})
        except ValueError:
            raise KeyError("give the numbers of the pieces you would act on, as 1 6, or the word none.") from None
        if act[0] < 1 or act[-1] > n:
            raise KeyError(f"{s['worker']} showed {n} pieces in {run.id}, numbered 1 to {n}.")
    note = f"would act on {', '.join(map(str, act)) or 'none'} of {n}" + (f". Why: {a.why}" if a.why else "")
    Step(run, s["id"]).score("would_act", len(act) / n, note=note)
    log.close()
    print(f"Recorded: you would act on {len(act)} of {n} pieces from {s['worker']} in {run.id} "
          f"({round(100 * len(act) / n)}%). If the loop works, this share rises run by run. Watch it with:\n"
          f"  kb log --db {a.runlog} workers --task advise --score would_act\n"
          f"If a piece was wrong for a reason that will come back, teach kb once:\n"
          f"  kb picture lesson \"your rule, in your own words\"")
    return 0


def _models(a, dump) -> int:
    from . import models
    from .models import config
    if a.mod_cmd == "init":
        if os.path.exists(a.file) and not a.force:
            raise KeyError(f"{a.file} is already there. Edit it, or add --force to write it again.")
        url = (a.url or config.LOCAL_URL).rstrip("/")
        probe = config.Model("probe", "openai", url, "probe", timeout=5)
        found, note = [], ""
        if models.place(url)[1] == models.HERE:
            try:
                found = models.offered(probe)
            except models.ModelError:
                note = (f"No runtime answered at {url}, so the file names no local model yet. Start your runtime "
                        f"and run this again with --force, or put a model's name in by hand.")
        else:
            note = f"{url} is not this machine, so kb did not ask it what it has. Fill the model name in by hand."
        os.makedirs(os.path.dirname(a.file) or ".", exist_ok=True)
        with open(a.file, "w", encoding="utf-8") as f:
            json.dump(config.example(found, url), f, indent=1)
            f.write("\n")
        print(f"{a.file} written" + (f" with {len(found[:6])} local models from {url}: {', '.join(found[:6])}." if found else "."))
        if note:
            print(note)
        print("It holds no key and never should. The \"key\" entry is used only when a run says --allow key.")
        return 0
    book = models.load(a.file)
    if a.mod_cmd == "list":
        rows = []
        for m in book.models.values():
            host, where = models.place(m.url)
            rows.append({"name": m.name, "default": m.name == book.default, "model": m.model, "host": host,
                         "where": where, "asked_freely": models.allowed(m), "protocol": m.protocol,
                         "key_from": m.key_env, "budget_chars": m.budget})
        dump(rows)
        return 0
    if a.mod_cmd == "check":
        out, bad = [], 0
        for m in ([book.get(a.name)] if a.name else book.models.values()):
            host, where = models.place(m.url)
            row = {"name": m.name, "model": m.model, "host": host, "where": where}
            if not models.allowed(m, a.allow):
                row["result"] = f"not asked: it is not on this machine. To check it, add --allow {m.name}"
                out.append(row)
                continue
            try:
                if m.protocol == "openai":
                    have = models.offered(m, a.allow)
                    row["runtime_offers"] = have
                    if not ({m.model, f"{m.model}:latest", m.model.removesuffix(":latest")} & set(have)):
                        row["note"] = f"the runtime does not list '{m.model}'"
                ans = models.ask(m, "You are a connection test.", "Reply with the single word: ready", allow=a.allow,
                                 sending="a connection test, nothing of yours")
                row.update(result="answered", said=ans.text.strip()[:60], ms=ans.ms, answered_by=ans.model)
            except models.ModelError as e:
                bad += 1
                row["result"] = f"failed: {e}"
            out.append(row)
        dump(out)
        return 1 if bad else 0
    if a.mod_cmd == "pick":
        from .runlog import RunLog, Step, query
        if not os.path.exists(a.db):
            raise KeyError(f"no run log at {a.db} (use --db PATH or set KB_RUNLOG)")
        log = RunLog(a.db)
        run = log.get(a.run)
        steps = [s for s in query.show(log, run.id)["steps"] if s["worker"] and s["status"] == "ok"]
        names = [s["worker"] for s in steps]
        if a.name not in names:
            raise KeyError(f"'{a.name}' gave no answer in {run.id}. Those that did: {', '.join(names) or 'none'}.")
        if any("picked" in s["scores"] for s in steps):
            raise KeyError(f"a pick is already recorded for {run.id}.")
        for s in steps:
            Step(run, s["id"]).score("picked", 1.0 if s["worker"] == a.name else 0.0, note="chosen by a person")
        print(f"Recorded: {a.name} was picked over {', '.join(n for n in names if n != a.name) or 'no other'} in {run.id}. "
              f"See the standing with: kb log --db {a.db} workers --score picked")
        return 0
    return 0


def _scout(a, dump) -> int:
    from datetime import date
    from . import models, scout
    from .picture import Picture
    today = date.fromisoformat(a.today) if a.today else date.today()
    ledger = scout.Ledger(a.ledger)
    if a.scout_cmd == "log":
        rows = ledger.rows()
        dump({"open": scout.open_now(rows, today), "rows": rows}) if a.json else print(scout.log_md(rows, today))
        return 0
    pic = Picture.load(a.file)
    if not pic.cards:
        raise KeyError("the picture holds no cards yet. Add some with: kb picture add CARDS.md")
    m = models.load(a.models_file).get(a.model)
    files = scout.sources(a.paths)
    if not files:
        raise KeyError(f"no .txt, .md or .html file in: {', '.join(a.paths)}")
    chars = sum(min(len(scout.read_source(f)), m.budget) for f in files)
    models.gate(m, a.allow, chars, f"{len(files)} saved sources and one line about each of your projects")   # before any run or line
    log, run = _open_log(a, "scout", m.name, f"{len(files)} sources")
    rows = scout.watch(pic, files, m, ledger, allow=a.allow, today=today, again=a.again)
    if run:
        for r in rows:
            if r.get("seen_before") or "ms" not in r and r["verdict"] != "error":
                continue
            v = r["verdict"]
            run.record("read", worker=m.name, version=r.get("model") or m.model, subject=os.path.basename(r["source"]),
                       status="failed" if v == "error" else "ok", error=r.get("reason") if v == "error" else None,
                       output={k: r.get(k) for k in ("verdict", "what", "for", "quote", "deadline", "reason", "notes")},
                       duration_ms=r.get("ms"), tokens_in=r.get("tokens_in"), tokens_out=r.get("tokens_out"),
                       cost=r.get("cost"), scores=None if v == "error" else {
                           "said_chance": float(v in ("opportunity", "unchecked", "closed")),
                           "confirmed": float(v in ("opportunity", "closed"))})
        run.end()
    if a.json:
        dump({"run": run.id if run else None, "rows": rows})
    else:
        print(scout.scout_md(rows, today))
        print(f"\nEvery reading is kept in {a.ledger}. See it all with: kb scout log")
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
