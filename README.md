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
| `knowledgebreeder/picture/` | The whole picture: one person's projects as one graph, read from cards. Overlaps, gaps, reuse, a brief, a town you can open offline, and advice written by a model, held to the cards and to the person's own lessons, with a rating per run and one page per run that puts every model's advice in one list, served to your phone if you like. Not tied to P&IDs. | Reports tested on invented cards. Advice tested against a stand-in server, and run for real four times: three on a local model offline, once beside an outside model the person allowed |
| `knowledgebreeder/models/` | The models kb may ask, and the gate. A model on your own machine is asked freely. Anything else needs your yes for that run. Ready entries for five providers. | Tested against a stand-in server only |
| `knowledgebreeder/scout/` | The scout: reads pages you saved against your projects, keeps what the text itself shows, and keeps a ledger of everything it read and passed over. | Tested against a stand-in server only |
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

## Advice and the scout

The reports above are rules. They find what is there. They cannot say what to do about it, and they cannot read a
page you saved. A model can do both, and a model can also make things up. So kb splits the work: it picks the
evidence, the model writes, and kb checks what the model wrote against the evidence before you see it.

### Which models, and where your data may go

kb asks the models you list in one private file, `work/models.json`. Make it on the machine that runs your local
runtime (Ollama, llama.cpp or LM Studio: anything that speaks the OpenAI chat protocol):

```bash
kb models init
```

It asks the runtime which models it has and writes one entry for each, plus a `key` entry for the Claude API. See
where each one lives:

```bash
kb models list
```

Check that they answer:

```bash
kb models check
```

The gate goes by address, not by name:

- A model on **this machine** (`localhost`, `127.0.0.1`) is asked freely. kb does not use a proxy for it and does
  not follow a redirect from it, so the prompt cannot be passed on.
- A model on **your own network** (an address such as `192.168.1.20`) is asked freely only when its entry says
  `"lan": true`. You write that yourself.
- **Anything else** is refused unless that run names it with `--allow NAME`. The refusal says how much would have
  been sent and where. Nothing is sent first.

A key never goes in the file. The entry holds the name of the environment variable (`"key_env"`), kb reads it at the
moment of the call, and it is not written to a log. A file that holds a key field is rejected. The key path uses
the official Anthropic SDK, which is an extra install:

```bash
pip install -e ".[key]"
```

The example `key` entry turns on `"fallbacks": "default"`: if the model declines a request, the API lets another
Claude model answer, and kb says which one did. Remove that line to turn it off.

#### Adding an outside model

kb has ready entries for five providers: `openai`, `gemini`, `kimi`, `deepseek` and `claude`. One command writes the
entry, keeps every other entry as it was, and tells you where to get a key, which variable it goes in, and what
the provider says it does with your data:

```bash
kb models add gemini
```

It then shows how to put the key in its variable without it showing on screen or landing in your shell history
(`read -rs GEMINI_API_KEY && export GEMINI_API_KEY`, then paste), how to check the model answers, and how to ask it
beside your local one. `--as NAME` gives the entry another name and `--model ID` another model at that provider.
Model names and prices change often: `kb models check NAME --allow NAME` shows what your key can really use. These
entries are outside models, so each run still needs `--allow NAME` (or `--allow a,b` for several).

Read what each provider says about your data before you send it cards about client work. The command prints it;
at the time of writing, DeepSeek's privacy policy says it stores data in China and may use it to train its models.

#### What never leaves this machine

Allowing an outside model for a run does not send it everything. A model on this machine sees every line. A model
anywhere else, on your network or outside, never gets a line from your cards, or a lesson, that holds:

- a phone number, an email address, a network address, or something that looks like a key or a token
- an amount of money: a number with a currency (`$`, `EGP`, `جنيه` and others)
- a name or word on your private list, `work/private.md` (or `--private PATH`, or the `KB_PRIVATE` variable)
- the mark `#private` (or `#خاص`) anywhere on the line

Put a name on the list with:

```bash
kb picture private "Corner kiosk"
```

and see the list with `kb picture private`. Put `#private` in a card's name or first line and the whole card stays
home, report lines that name it included. kb drops such a line before it numbers the evidence, so the model never
learns it was there. The gate's message, `--show-prompt`, the answer, the page and the run log all say how many lines
stayed home and of which kind, never what they said. The scout does the same with your project list. If every line
would stay home, nothing is sent and kb says so.

This is pattern matching. It will miss some private things (a client's name you did not list) and hold back some
harmless ones (`5 pounds of flour`). The list and the mark are how you correct it, and a model on this machine is how
you use everything.

Text that someone else wrote can carry orders aimed at a model: "ignore your rules and ...". Every prompt says the
evidence is data. kb also marks each line that reads like such an order where the model reads it, drops a piece of
advice that rests only on marked lines, and does not take a scout quote that comes from one. That is a guard, not a
proof: a model can still be swayed, which is why you read and sign.

A local runtime may cut a long prompt to fit its context window without saying so. kb therefore sends a local model
a bounded amount (`"budget"`, 8,000 characters by default), tells you how many lines did not fit, and warns when the
token count the runtime reports is far too low for what was sent. Raise `budget` in the entry when your runtime's
window allows it.

### Advice

```bash
kb picture advise
```

kb sends numbered lines from your cards and from the rule reports. The model must name the lines each piece of
advice rests on. kb then drops any piece that rests on no line it sent and says how many it dropped, marks any
figure that is in none of the cited lines, and prints each piece with the card and heading it came from. The model
is named at the top.

See exactly what would be sent, and send nothing:

```bash
kb picture advise --show-prompt
```

One project in depth:

```bash
kb picture advise --project "Saturday baking class"
```

A hard question, to the key, with your yes for this run:

```bash
kb picture advise --model key --allow key
```

Add `--lang ar` for advice in Arabic.

### The same question to several models

```bash
kb picture advise --models local,local-2
```

Each model answers on its own and the run log keeps them side by side: time, tokens, how many pieces passed the
check. Those numbers are a floor, not a judgement. Whether advice is any good is yours to say. When you have read
them, record the one you would act on:

```bash
kb models pick RUN local-2
```

Over time the run log shows which model you keep choosing:

```bash
kb log workers --task advise --score picked
```

### Teach it, run by run

A model repeats its habits. When a piece of advice is wrong for a reason that will come back, write the reason down
once, in your own words:

```bash
kb picture lesson "Quiet is not dead. Do not suggest archiving a project only because it has been quiet."
```

Lessons live in one private file, `work/lessons.md`, one per line. Edit or delete lines by hand whenever you like.
List them with `kb picture lesson`. Every advice run sends them as standing rules that outrank the model's own
judgment, and says at the top how many it followed. They are rules, not evidence, so no piece of advice may cite one.
If there are more than about 4,000 characters of lessons, the newest are sent and kb says how many older ones were
left out. A lesson goes wherever the advice goes: to a model off this machine only with `--allow NAME`, and the
refusal counts your lessons in what would have been sent.

After a run, mark the pieces you would act on. The easiest way is the page (next section), which writes the command
for you. In the terminal, give the run id kb printed (a unique start of it is enough) and the numbers of the pieces:

```bash
kb picture rate run_4f1c9a2b7d3e 1 6
```

Add `--why "..."` to keep a reason with it, `--worker NAME` when the run asked several models, or the word `none`
when you would act on none. When a piece is nearly right, say it your way with `--change 2 "your version"`; add
`--keep 2` to make that change a lesson for every run too. Your words are kept with the rating, and the page shows
them on the idea from then on. The share of pieces you would act on is stored as the score `would_act`. If the lessons
work, it rises run by run:

```bash
kb log workers --task advise --score would_act
```

To see what the lessons change, ask the same question without them:

```bash
kb picture advise --no-lessons
```

kb cannot check that a model followed a lesson. Your rating is that check. Each run records the lessons it was given,
so a lesson that does not raise the share can be found and rewritten. Nothing here retrains a model: the lessons are
read again on every run, and you can see and change every word.

### One page for every answer

The terminal is the engine. To read a run, open it as one page:

```bash
kb picture page --open
```

It takes your newest advice run, or the one you name (`kb picture page RUN`), and writes `work/advice/RUN.html`:
one file that opens with no internet and asks the network for nothing.

- Every model's pieces are in one list. Each piece keeps its model's name and its own number, so a rating still
  credits the right model.
- Pieces from different models that cite the same lines of your cards are put together and shown first. The match
  is made from the lines cited and the words used, not from meaning. The same advice from two models counts twice;
  two different answers on the same lines are worth reading side by side.
- Each piece shows the lines it cites, so you can check it where you read it.
- Tick what you would act on, and choose the better answer if the run asked several models. Under each piece,
  "Change it" opens a box to say the idea your way, with a tick to keep it as a lesson for every run. The page
  writes the exact `kb picture rate` and `kb models pick` commands, each with a Copy button. The page itself saves
  nothing: you paste the commands, and kb records them. Once recorded, the page says back what kb holds: the
  pieces, your reason and your changes, in your words.
- At the bottom, a table shows, run by run, the share of each model's pieces you said you would act on, and whom you
  picked. That is how a model earns its place, or loses it.
- Below it, folded away until you open it, is the run's trail (next section).

`--lang ar` writes the page in Arabic. It holds lines from your cards, so it stays in `work/`, which is never
committed.

### The trail of a run

Every advice run is a piece of work done by you and one or more models together. kb records each step of it in the
run log as it happens, so it can say afterwards who did what, in the eight fields of a Vn-trail (Momtaz, 2026, "The
Vn-Trail: A Method for Inspectable Human-AI Collaboration in Scholarly Work", SSRN 6739158): the step, what
started it, what was added, removed and reframed, who started the move, why, and what each side brought.

- V0 is your ask: the lines of your cards and the lessons sent, and to whom. HUMAN.
- One entry per model's answer: its pieces, and any kb dropped for citing no line it sent. AI.
- One entry per verdict you saved: what you would act on and what not, and why. HUMAN.
- One entry per change you made to an idea, from the model's words to yours. DIALOGUE: neither side alone would
  have written it.
- Your pick, if the run asked several models. HUMAN.
- While some answer still waits for your verdict, the trail ends with a "forthcoming" row. It claims to be
  faithful, not complete.

```bash
kb picture trail
```

prints the newest run's trail as a table; name a run to see another, add `--json` for one line per step (for coding
many trails at once), `--all` for every advice run, `--lang ar` for Arabic. On the page, the trail sits closed at the
bottom, with a one-line count of HUMAN, AI and DIALOGUE steps; open it only when you want it.

### On your phone

Ideas come on the phone, so the pages can be read and rated there too, with no commands to paste:

```bash
kb serve --open
```

`kb serve` shows every advice run as a list, newest first, with what you have recorded for each. Each run opens as
the same page, but with a Save button where the commands were: ticks, the "none" box, your reason and your pick are
recorded by kb as you press it, through the same rules as `kb picture rate` and `kb models pick`. Your changes to
ideas save with the ticks, and a ticked "keep it as a lesson" adds the lesson at the same press. After Save, the page
comes back to what kb recorded, marked "Saved", with your words in it. You can add a lesson from the list page too.

It listens on `127.0.0.1` only, so nothing on your network or the internet can reach it. To reach it from your phone,
put [Tailscale](https://tailscale.com) on the laptop and on the phone, signed in to the same account, and run once:

```bash
sudo tailscale serve --bg 8765
```

Tailscale prints an address ending in `.ts.net`. Open it on the phone. Only devices on your own tailnet can, and the
connection is encrypted. `sudo tailscale serve reset` takes it off again. Never use `tailscale funnel` (or ngrok, or
a router port) for this: that would put your cards on the internet.

kb serve also refuses requests that name another host (a web page cannot reach it by renaming an address), takes
changes only as JSON with its own header (a page from another site cannot send them), and tells the browser to keep
nothing and load nothing from outside. When Tailscale says who opened the page, the list shows it.

### The scout

Save pages into a folder as `.txt`, `.md` or `.html`: a call for proposals, a newsletter, an announcement. Then:

```bash
kb scout read work/sources
```

For each source the scout finds the cards it shares words with, asks the model whether the text holds a real chance
for one of your projects, and checks the answer against the text. The quote must be in the source word for word. The
words that give the deadline must be in it too, with the same day and year. A project the model names must be one
kb offered. What passes is listed under **Chances**, the nearest deadline first. What the model claimed and kb could
not confirm is listed apart. Nothing is dropped silently.

Every reading goes into a ledger, `work/scout.jsonl`, whatever the verdict:

```bash
kb scout log
```

It lists the chances still open today, and every source the scout passed over with the reason it gave. If a real
chance sits under "Passed over", the scout missed it, and now you know.

Limits: advice has run against two real models so far (November 2026): a 27-billion-parameter model on a laptop,
offline, and once an outside model, allowed for that run. The scout has not run against a real model yet. The tests use a stand-in server that returns canned answers,
so they prove what kb does with an answer, good or bad, and say nothing about how good a real model's advice is. The checks catch a citation to a line that was never sent, a quote that
is not in the source, and a figure or deadline that is not there. They do not catch advice that cites real lines and
is still wrong, so a person reads it and signs. The scout reads what you save. It does not search the web, and no
tool can promise that no chance is ever missed. It checks a deadline's day and year against the quoted words, not
the month. Matching by words is weak across languages, so an Arabic page against English cards relies on the model.
A saved page is someone else's text: the model is told to treat it as data, and kb believes nothing about it that
the text does not show, but a page written to mislead can still waste your time. The run log stores the evidence
lines that were sent, so treat `runs.db` and `work/` as private.

## Your agents

An agent is any program that reads your data and does something with it by itself: a bot that answers customers, a
script that posts a weekly sheet, a model that writes code. Each one should have a record, the way a person on a
team has a staff file. Make the file once:

```bash
kb agents init
```

It writes `work/agents.md` (or `--file PATH`, or the `KB_AGENTS` variable), which is private. Fill in one block per
agent, in your own words; only the name is needed:

```text
name: Shop replier
does: answers questions on the shop page
runs: outside (a hosting service)
reads: customer messages; the price list
sends: api.example.com
keys: SHOP_MODEL_KEY
may: send, reply
ratifies: nobody
owner: Nour
stop: switch off the page's chat box
passes: Weekly totals
last_run: 2026-11-18
```

Then see the register, with kb's own models added from your models file and their last run read from the run log:

```bash
kb agents
```

The fields follow the five layers of ARM, Agent Resource Management (Momtaz, 2026, SSRN 6380498): the owner is the
accountability chain, the register is the stewardship register, who ratifies is the prospective review, how to stop
it is the override protocol, and whom it passes work to is the inter-agent council. What needs a look is a gap in a
layer: an agent that may send, pay or change things with nobody ratifying first; work that leaves this machine and
your network with nobody's yes, also through an agent it passes work to; no owner; no written way to stop it; a
name from your private list in what it reads while its work leaves; a key still held months after the last run;
one key shared by two agents; work passed to an agent with no record.

A key goes in by its variable's name. A file that holds what looks like a real key is refused, and kb does not
print the key back. kb reads what you wrote and does not inspect the agents, so a record is only as true as its
writer. `--json` gives the register and the findings as data.

## Limits, plainly

- No method reads every connection on a real P&ID correctly. An engineer must review the graph before it is used for
  design, operations, management of change or safety studies. The use layer gives connectivity answers only: it
  knows nothing of pressures, hold-up or procedures.
- The vector reader has been tested on synthetic pages, not yet on a real CAD export. Real exports are messier
  (text drawn as outlines, hatching, symbols made of many strokes). It ignores curved pipes and does nothing for scans.
- The vector reader is not yet wired into the seed's extraction step. That is the first candidate in
  `breeding/candidates.md`, and it must earn its place with a score.
- `kb serve` serves while its terminal is open; it is not a background service. The phone reaches it only while the
  laptop is on and awake. Its safety rests on staying on `127.0.0.1`, with Tailscale as the only way in.
- No accuracy number is claimed for this repo yet. `breeding/scores.jsonl` will hold them as they are measured.

## Credits and licence

MIT. The seed skill is by Scott Duncan, MIT, kept unchanged with its licence; see [NOTICE.md](NOTICE.md).
