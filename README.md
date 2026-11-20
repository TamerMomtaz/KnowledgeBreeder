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
| `knowledgebreeder/walk/` | Walk the plant: the graph drawn as one page that opens offline. Pick an item and see what stops with it or which valves box it in. | Tested on a demo plant; not yet on a real one |
| `knowledgebreeder/scoreboard/` | Scores a graph against a checked gold file, keeps a ledger, and holds the promotion rule. Also a PID2Graph loader. | Scorer tested; PID2Graph loader not yet run on the real download |
| `knowledgebreeder/runlog/` | The run log: what every worker saw, said, cost and scored, in one SQLite file. Leaderboard and run-to-run comparison. Not tied to P&IDs. | Tested |
| `knowledgebreeder/picture/` | The whole picture: one person's projects as one graph, read from cards. Overlaps, gaps, reuse, a brief, and a town you can open offline. Not tied to P&IDs. | Tested on invented cards; word matching only, no model yet |
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

## Walk the plant

`kb walk` draws the graph as one HTML file. The source is on the left and the sink on the right. Branches sit in
rows under the line they leave, instruments are circles above what they measure, and a recycle runs back under
the plant.

```bash
kb walk tests/fixtures/demo_graph.json --out work/demo-plant.html
```

```bash
kb walk work/<plant>/kg --out work/plant.html --lang ar
```

Pick an item to read it, then choose **If it stops** or **To isolate it**. The page greys out what loses its
supply, marks the instruments that go blind, colours the valves to close and outlines the equipment no valve
shuts it off from. The mode stays on while you walk, so each step down the line shows what that item would take
with it. The arrow keys walk the line, and every item is also a plain button in a list.

What the marks mean: a dashed pipe is a flow direction the reader guessed, a dashed outline is an item read with
low confidence, a number is how many items starve if that one stops, and a question mark is an open question
from `kb research`. Single points, the questions and the numbers are in the same file.

Every answer on the page is worked out by the same code as `kb whatif`, for every item, when the file is made.
The page only shows them. It switches between English and Arabic.

Limits: kb chose where things stand. Only the connections come from your drawing, so the page will not look
like your P&ID. The whole plant is one drawing with no split by sheet, which gets long for a large plant. A line
that crosses another is drawn straight over it. The what-if answers are connectivity only, as everywhere in the
use layer. The file holds your plant, so treat it as private. It asks the network for nothing, and a content
security policy inside it forbids it. Arabic covers the page's own words, not tags, kinds or the questions.

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

## The whole picture

The same idea as the plant graph, pointed at a person. A plant is equipment tied by pipes. A person's work is
projects tied by what they share, need and could lend each other. `kb picture` reads that from **cards**.

A card is what one project says about itself under fixed headings: what exists, what it can do, what it needs,
what is unfinished, what could travel, what it links to. Any assistant that holds a project can write one with
the prompt in `knowledgebreeder/picture/inventory-prompt.md`, and you can write one by hand for anything that
lives in no tool. "unknown" is kept as a fact and never filled in.

Try it on the invented example:

```bash
kb picture --file tests/fixtures/demo_cards.md brief
```

```bash
kb picture --file tests/fixtures/demo_cards.md town --out work/demo-town.html
```

With your own cards, merge them into your picture first. Adding a card again replaces the older one.

```bash
kb picture add my-cards.md
```

```bash
kb picture add --area "Painting"
```

```bash
kb picture overlaps
```

```bash
kb picture gaps
```

```bash
kb picture reuse
```

```bash
kb picture brief
```

```bash
kb picture town --out work/town.html --lang ar
```

- **Overlaps**: the same idea in more than one project (from each card's recurring themes), overlaps the cards
  state themselves ("same list, kept twice"), and projects described in similar words.
- **Gaps**: needs not met, work started and not finished, decisions waiting, things a card names that have no card,
  a name that fits two cards, areas you named and never described, projects tied to nothing, projects gone quiet,
  and everything left as unknown.
- **Reuse**: a part one card offers to a named project, a part that may answer a need elsewhere, and parts offered
  to everything.
- **Brief**: a short list of moves worth a look, each with why and the card and heading it came from.
- **Town**: the picture as one HTML file. An area is a district and a project is a building. Height is how many
  other projects it is tied to. Lit windows mean recent work. A flag is a decision waiting and a crane is unfinished
  work. An area with no card is an empty lot. Pick a building to read its card and see what it is tied to. The four
  reports are in the same file. It switches between English and Arabic, works by keyboard, and every project is
  also a plain button in a list.

Your picture is private. It is one local file, `work/picture.json` by default, and `work/` is ignored by git.
The town file holds your picture too, so treat it the same way. The page asks the network for nothing, and a
content security policy inside it forbids it.

Limits: everything here is counting and word matching over your cards. It does not understand them, it does not
call a model, and it does not look outside the picture. A "word match" is a hint to look, not a finding. Names are
tied to cards by their words, so a card can carry an `aliases:` line to help, and a name that fits two cards is
reported, not guessed. The Arabic labels cover the page, not the text of your cards or the sentences in the
reports.

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
