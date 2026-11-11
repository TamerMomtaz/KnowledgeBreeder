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

The graph argument is a graph.json, or the folder holding one.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read"); r.add_argument("pdf"); r.add_argument("--page", type=int, default=1)
    r.add_argument("--reader", default="vector_geometry"); r.add_argument("--rotation", type=int, default=0)
    r.add_argument("--out")
    for name in ("stats", "describe", "research"):
        s = sub.add_parser(name); s.add_argument("graph"); s.add_argument("--json", action="store_true")
    b = sub.add_parser("brief"); b.add_argument("graph"); b.add_argument("tag")
    w = sub.add_parser("whatif"); w.add_argument("graph"); w.add_argument("action", choices=["fail", "isolate", "spof"])
    w.add_argument("tag", nargs="?")
    sc = sub.add_parser("score"); sc.add_argument("graph"); sc.add_argument("gold")
    sc.add_argument("--log", help="append the headline numbers to this ledger (JSON lines)")
    sc.add_argument("--label", default="run"); sc.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    def dump(x):
        print(json.dumps(x, indent=1, ensure_ascii=False))

    if a.cmd == "read":
        from .readers import get
        res = get(a.reader).read(a.pdf, a.page, a.rotation).to_dict()
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=1)
            print(f"{a.out}: {res['stats']}")
            for wmsg in res["warnings"]:
                print("warning:", wmsg)
        else:
            dump(res)
        return 0

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
            with open(a.gold, encoding="utf-8") as f:
                res = sb.score(pg, json.load(f))
            dump(res)
            if a.log:
                print("logged:", sb.log(res, a.log, a.label, a.note))
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
