"""The run log: what every worker saw, said, cost and scored.

A *run* is one attempt at a task. A *step* is one piece of work inside it,
done by a *worker* (a reader, a model, a script, a person) on a *subject*
(a page, a file, a question). A *score* is a number attached to a step or run.

Nothing here knows about P&IDs. The same log serves any task where several
workers attempt the same subjects and the best one should win, which is how
one input can be fanned out to many workers and judged on evidence.

It is one SQLite file: no server, works offline, safe for several processes
writing at once.

    from knowledgebreeder.runlog import RunLog
    log = RunLog("work/runs.db")
    with log.run(task="read-pid", label="baseline", subject="haile.pdf") as run:
        with run.step("read", worker="vector_geometry", version="0.1.0", subject="page_03") as s:
            s.output = reader.read(pdf, 3).to_dict()
            s.score("pipe_runs", 12)
"""

from .log import Run, RunLog, Step
from . import query

__all__ = ["Run", "RunLog", "Step", "query"]
