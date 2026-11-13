# KnowledgeBreeder

**Engineering drawings in. A knowledge graph out that gets better every run, and four ways to multiply what you do with it.**

It starts from P&IDs (piping and instrumentation diagrams) and is built so other documents can be added later.

```
 P&ID PDF ──► READERS ──► plant graph ──► USE
               │  ▲                        ├─ statistics    measure the plant and the graph
               │  │                        ├─ synthesis     describe it for people and LLMs
               ▼  │                        ├─ manipulation  what-if: fail it, isolate it
            SCOREBOARD ◄── gold files      └─ research      questions worth checking
               │
               ▼
            BREEDING: a challenger replaces a champion only when the score goes up, and a person signs
```

## What is here

| Part | What it does | State |
|---|---|---|
| `seed/pid-to-kg/` | Scott Duncan's [pid-to-kg](https://github.com/ScottDuncanAI/PID-to-Knowledge-Graph) Claude skill, unchanged. Claude reads each sheet; scripts build `graph.json`. | Upstream v0.1.0 |
| `knowledgebreeder/readers/` | Plug-in readers. The first one, `vector_geometry`, pulls the pipe network straight out of a vector PDF as exact coordinates: runs, tees, boxes, symbols, tags. | Tested on synthetic pages only |
| `knowledgebreeder/use/` | The four use modules, all working on `graph.json`. | Tested on a demo plant |
| `knowledgebreeder/scoreboard/` | Scores a graph against a checked gold file, keeps a ledger, and holds the promotion rule. Also a PID2Graph loader. | Scorer tested; PID2Graph loader not yet run on the real download |
| `knowledgebreeder/runlog/` | The run log: what every worker saw, said, cost and scored, in one SQLite file. Leaderboard and run-to-run comparison. Not tied to P&IDs. | Tested |
| `breeding/` | The improvement loop: candidates, the growth prompt, the ledger. | No schedule set up yet |

## Quick start

```bash
pip install -e ".[dev]"
```

```bash
pytest -q
```

Try the use layer on the demo plant:

```bash
kb describe tests/fixtures/demo_graph.json
```

```bash
kb brief tests/fixtures/demo_graph.json TK-102
```

```bash
kb whatif tests/fixtures/demo_graph.json fail CV-0502
```

```bash
kb research tests/fixtures/demo_graph.json
```

Pull the pipe skeleton out of a vector P&ID page:

```bash
kb read drawing.pdf --page 3 --out skeleton_p3.json
```

## From your own drawings

1. Install the seed skill (copy `seed/pid-to-kg` into `~/.claude/skills/`) and ask Claude Code to convert your PDF.
   It writes `work/<plant>/kg/graph.json`.
2. Point any `kb` command at that folder: `kb stats work/<plant>/kg`.
3. Check a sheet by hand, write it down as a gold file (format in `knowledgebreeder/scoreboard/score.py`), and score:
   `kb score work/<plant>/kg gold.json --log breeding/scores.jsonl --label baseline`.

## The four uses

- **Statistics** (`kb stats`): counts by kind, sources and sinks, longest path, busiest equipment, equipment with no
  instrument, control valves outside loops, and how far the graph can be trusted (confidence, inferred directions).
- **Synthesis** (`kb describe`, `kb brief TAG`): a source-to-sink description of the plant, or one card per item that
  pulls together flow, instruments, loops, failure effect, isolation and open questions.
- **Manipulation** (`kb whatif`): `fail TAG` shows what loses supply, which instruments go blind and which loops are
  hit; `isolate TAG` lists the valves to close and where there is no valve; `spof` ranks single points of failure.
  It works on a copy and never edits the graph.
- **Research** (`kb research`): process-design rules turned into questions. A pump with no discharge pressure gauge, a
  vessel with no level instrument, a control valve in no loop, parallel pumps of unknown duty. Each says where to look.

## The run log

Every piece of work can be recorded: which worker did it (a reader, a model, a script, a person), on which subject
(a page, a file, a question), how long it took, what it cost and how it scored. The log is one SQLite file. It needs
no server, works offline, and several processes can write to it at once.

It knows nothing about P&IDs, on purpose. Any task where several workers attempt the same subjects can use it, and
that is what lets one input be fanned out to many workers and the winner picked on evidence.

Record from `kb` itself:

```bash
kb read drawing.pdf --page 3 --out skeleton_p3.json --runlog runs.db
```

```bash
kb score work/plant/kg gold.json --runlog runs.db --worker seed --version 0.1.0 --subject D-001
```

Record work done elsewhere, such as a model reading a sheet:

```bash
RUN=$(kb log --db runs.db start --task read-pid --label baseline --subject haile.pdf)
```

```bash
kb log --db runs.db step $RUN --name extract --worker model-name --subject page_03 --tokens-in 41000 --tokens-out 3200 --ms 95000 --score tags_f1=0.94
```

```bash
kb log --db runs.db end $RUN
```

Ask it questions:

```bash
kb log --db runs.db workers --score flow_f1
```

```bash
kb log --db runs.db compare RUN_A RUN_B
```

`workers` is the leaderboard: one row per worker and version, with mean score, how many steps that mean rests on,
time, tokens and cost. `compare` names the subjects where the challenger got worse or better. `runs`, `show`,
`failures` and `export` do what they say. From Python: `from knowledgebreeder.runlog import RunLog`.

Limits: token and cost numbers are whatever the caller reports; the log does not measure them. Inputs and outputs
over 256,000 characters are stored as a hash and a preview. `compare` assumes a higher score is better.

## Limits, plainly

- No method reads every connection on a real P&ID correctly. An engineer must review the graph before it is used for
  design, operations, management of change or safety studies. The use layer gives connectivity answers only: it
  knows nothing of pressures, hold-up or procedures.
- The vector reader has been tested on synthetic pages, not yet on a real CAD export. Real exports are messier
  (text drawn as outlines, hatching, symbols made of many strokes). It ignores curved pipes and does nothing for scans.
- The vector reader is not yet wired into the seed's extraction step. That is the first candidate in
  `breeding/candidates.md`, and it must earn its place with a score.
- No accuracy number is claimed for this repo yet. `breeding/scores.jsonl` will hold them as they are measured.

## Credits and licence

MIT. The seed skill is by Scott Duncan, MIT, kept unchanged with its licence; see [NOTICE.md](NOTICE.md).
