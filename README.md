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
| `knowledgebreeder/process/` | Layer 2, work processes from plain speech: each person says their job in their own words, and kb joins the hand-offs into one process (steps, pipes, valves, instruments, decision tables, joins), drawn as a plant graph. Not tied to P&IDs. | First step. Tested on three invented notes; no real voice note yet |
| `knowledgebreeder/thoughts/` | Layer 3, understanding: your cards, framed books and inbox as one map of thoughts, joined by needs, causes, is part of and contradicts. Answers to your questions with their sources, the gaps, marriages of thoughts you approve, and a city you can open offline. Not tied to P&IDs. | First step. Tested on invented cards, one invented book and one invented post, against a stand-in server; no real model run yet |
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

## Work processes from plain speech

A plant is equipment tied by pipes. A team is people tied by hand-offs. `kb process` reads each person's own
description of their job, one file per person, and joins them into one process you can read, walk and test like a
plant.

```text
person: Mona
job: order desk

I get the order from the customer.
I check the order is complete.
If the order is over 50 boxes, I send it to Karim for approval.
Otherwise I send it to the kitchen.
```

Try it on the three invented notes:

```bash
kb process show tests/fixtures/process
```

```bash
kb process show tests/fixtures/process --lang ar
```

```bash
kb process graph tests/fixtures/process --out work/process/graph.json
```

```bash
kb walk work/process/graph.json --out work/process/walk.html
```

```bash
kb process whatif tests/fixtures/process --stop "the bank"
```

kb knows seven kinds of sentence, in English and in Arabic. Anything else is kept as a step, word for word.

| Said | Becomes |
|---|---|
| I get THING from WHO · أستلم THING من WHO | a step that receives: one end of a pipe |
| I send / pass / give THING to WHO · أرسل / أسلم THING إلى WHO | a step that hands on: the other end |
| I wait for all of / any of / one of: A from X, B from Y · أنتظر كل من / أي من / واحد من | a join |
| I check / measure / count WHAT · أتحقق من / أراجع / أقيس WHAT | an instrument on the step before it |
| If CONDITION, ... · إذا CONDITION، ... | a valve, and a row in its decision table |
| Otherwise ... · وإلا ... | the decision table's last row |
| anything else | a step |

A file may also say `job:` and `also:` (other names the person goes by, such as "the kitchen"), so "I send it to the
kitchen" finds the person whose job that is. Someone named who has no file of their own is an outside party: a source
if they give, a sink if they get.

- **Hand-offs** are matched by the two names and the words of the thing. "It" or "them" matches whatever the other
  side says. A hand-off both sides describe is drawn solid. One that only one side describes is drawn dashed and is a
  question for the other person.
- **Joins** say how a step's inputs combine. **All of**: it needs every one. **Any of**: one is enough. **One of**:
  exactly one comes. A step with several inputs and no join word said is a question, and counted as all of until
  someone answers.
- **What if** (`kb process whatif --stop`): a person, a step (such as `"Sami 2"`) or an outside party stops, and kb
  lists what stops with them, which checks are lost, who is left waiting, and which steps keep going because they
  need any one of their inputs. `kb whatif` on the graph file counts connections only and does not know the join
  types; `kb process whatif` does.
- **Questions worth asking**: a hand-off one side does not mention, a join nobody stated, a decision with no
  "otherwise", a thing that arrives and nobody says they check, and a wait that says nothing of where it comes from.

The graph file is in the plant graph's own format: steps are equipment, hand-offs are pipe segments named by the
thing, decisions are components of kind `decision`, checks are instruments, and the decision tables and questions
ride along in the file. So `kb walk`, `kb stats` and `kb whatif` read it as they read a plant, with their plant words.

Your team's notes are private: keep them and the graph in `work/`, which is never committed.

Limits: this is pattern matching on words, not understanding. A sentence said another way ("Karim gets it next")
is kept as a plain step and joins nothing, so read the hand-offs list. The three notes in the tests are invented;
the process has not yet been tried on real voice notes, and kb has no speech reader yet, so a voice note must be
typed out first. The walk page still uses the plant's own words. Arabic covers kb's words and the sentence kinds
above, not every way of saying them.

## Understanding: the city of thoughts

The same idea again, pointed at what you know. A plant is equipment tied by pipes, and a team is people tied by
hand-offs. What you know is thoughts tied by what they need, cause, belong to and contradict. `kb thoughts` keeps
them in one private map, `work/thoughts.json`, and draws it as a city.

**What goes in.** Your project cards, all of them as one subject ("My projects"). Every book the frame-outer has
framed, each its own subject. Your inbox items: posts, links and PDFs. kb reads the cards and books by rules every
time a `kb thoughts` command runs. A model reads the inbox items when you ask it to.

```bash
kb thoughts
```

```bash
kb thoughts read --model local
```

```bash
kb thoughts ask "How do I find a delivery driver?" --model local
```

```bash
kb thoughts gaps
```

```bash
kb thoughts marry --model local
```

```bash
kb thoughts city --out work/thoughts/city.html --lang ar
```

- **A thought** is one idea in one sentence, kept with where it came from: the card and its heading, the book, or the
  inbox item and the lines the model read it from.
- **Its kind** is what it is in the city. **Infrastructure** is a principle other ideas stand on, drawn as a wide
  hall. A **resource** is a fact or a thing that exists, drawn as a store with a dome. A **utility** is a method or a
  tool you can use again, drawn as a tower with a mast. A **need** is something missing, drawn as an empty lot with a
  sign, waiting for a thought that helps it. On a card, recurring themes and ideas are infrastructure, what it can do
  and its reusable parts are utilities, what exists is a resource, and a need not yet met is a need. A book's
  principles are infrastructure.
- **Joins.** A model joins thoughts with one of four words: needs, causes, is part of, contradicts. Each join must
  rest on lines of the item it read. And whenever a thought arrives, kb at once joins it, by the telling words they
  share, to up to three thoughts from other sources: what you already have that **may help** it, or the need it may
  help. A "may help" join is a word match, a hint to look, and the page says so.
- **Reading the inbox** (`kb thoughts read`). kb numbers the item's lines and lists the thoughts on your map nearest
  to it. The model writes the item's thoughts, each citing its lines, and joins them to each other or to yours. kb
  then drops any thought that cites no line it sent, and any join of another kind, between thoughts it does not know,
  or with no line under it. It marks a figure that appears in none of a thought's lines, and says how many it
  dropped. An item is read once. `--again` reads it again.
- **Asking** (`kb thoughts ask`). kb sends your question and the thoughts nearest it, with the thoughts joined to
  them. The model answers in sentences, and each sentence must cite the thoughts it rests on. kb drops any sentence
  that cites none, and shows each one with its sources: the card, the book or the inbox item. **Gaps** are what the
  model says the map does not hold, marked as its words, and the words of your question that no thought holds. When
  no thought is near the question, nothing is sent. `--no-model` lists the nearest thoughts and their sources, with
  no model.
- **Marriages.** Two joined thoughts from different subjects can marry into a new one. `kb thoughts marry` lists
  the pairs. `--model NAME` asks a model to write the new thought for up to three pairs. A pair that makes nothing
  new is kept as such and not asked again, and a figure in neither parent is marked. Nothing joins the map until you
  say yes: `kb thoughts approve ID`, or `kb thoughts decline ID`, which is kept so the pair is never proposed again.
  To write the new thought yourself, use `kb thoughts marry A B --as "the new thought"`. It needs no approval. An
  approved thought stands in the district "Married thoughts" with a gold ring, names its two parents, and is joined
  at once like any newcomer, so it can marry again.
- **Gaps** (`kb thoughts gaps`): inbox items waiting for a model, screenshots and voice notes waiting for a reader on
  this laptop, books not yet framed, thoughts that contradict each other, needs nothing on the map helps yet,
  subjects with one source only, thoughts joined to nothing, and marriages waiting for your yes.
- **The city** (`kb thoughts city`): one HTML file, drawn like `kb picture town`. Each subject is a district, and a
  building is taller the more it is joined. Pick a building, or its name in the list under its district, to read the
  thought, where it came from, the source's own words and what it is joined to. The thoughts it is joined to light
  up. Find a thought by a word, or show one kind only. Marriages waiting for your yes are listed with the commands to
  approve or decline them, each with a Copy button. The page saves nothing itself. Each control has a line saying
  what it does. The page switches between English and Arabic, works by keyboard, and asks the network for nothing.

What a model off this machine is sent follows the same rules as advice. It needs `--allow NAME` for that run. It
never gets a line or a thought that holds a name on your private list, #private, a phone, an email, a key or money,
or any thought from a card marked #private. A question that holds one of these is not sent at all. Every run goes
into the run log with its cost (`thoughts-read`, `thoughts-ask`, `thoughts-marry`).

Nothing is overwritten. When a line leaves a card, its thought is kept and marked with the day it left, and it
leaves the city. A declined marriage is kept. The map is private: it stays in `work/`, which is never committed,
and so does the city file.

Limits: "may help" is word matching, not understanding. Two thoughts that say the same thing in different words are
not joined, and two that share words by chance are. A model reads only the first part of a long item, as much as
fits its budget, and the command says how many lines were left out. The thoughts a model writes are its reading:
the check proves each one cites real lines, not that it reads them rightly. So read the source's words under each
thought before you build on it. While `kb serve` runs, the model on this laptop reads each new inbox item into the map as it
arrives (and every half hour, for anything left over), and each inbox line on the page says what became of it: how
many thoughts, in which subject, how many links to what you had, or why it is not in the map yet. Only a model on
this laptop reads this way, so nothing you send leaves the laptop for it. The page has no Ask box for the map yet. Arabic covers the page and
kb's own words, not the thoughts, which keep the words they were written in.

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

With your own cards, merge them into your picture first. Adding a card again keeps the older one (see below).

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

### Is it ready for a model?

```bash
kb picture check
```

asks every card the five questions of a data-ready check: does it say when the project was last worked on, how much
of it is filled in, where its facts come from (and whether that is more than memory), whether one project goes by
two names (or one name fits two cards, or an area is written two ways), and who keeps its facts true. A card with no
gap is ready, with one gap thin, with two or more weak; the weak ones are listed first, with what is missing. A card
can name its owner with an `owner:` line in its header, for facts that belong to someone else, such as a client.

"A model is only as useful as the data under it" is a claim, and your ticks can test it. Every advice run records
which cards were weak at the time and marks each evidence line that rests only on weak cards. The model is not told,
and the page marks such a piece. `kb picture check` then counts, over your rated runs, how many pieces you would act
on when they rest only on weak cards, against the rest. It waits for five rated pieces on each side before it says
the numbers mean anything.

### Nothing overwritten

When you add a card that the picture already holds, and it now says something else, the new one becomes the
current card and the older one is kept, with the day kb learned it and a fingerprint of the file it came from. The
same card added again changes nothing. `kb picture add` says, for each card that changed, what left it.

To rename a project, give its card the new name and a `formerly:` line with the old one, such as
`formerly: Bakery van`. The card under the old name becomes the renamed card's older version, with its history, so
the picture holds one card and nothing is lost. Without that line, a new name is a new card.

```bash
kb picture changes
```

shows, for every card with older versions:

- **No longer on a card**: every idea, need, unfinished piece of work or open decision that was on a card once and
  is not now, with the day it was last seen. kb cannot tell whether it was done, dropped or forgotten. You can, and
  a forgotten one is a chance found before it is missed. The brief lists the newest two, and advice runs get them
  as evidence lines, through the same private-list check as every other line.
- **The newest version against the one before**: header lines that changed, items that came and went, and needs
  that changed from not met to met. An item reworded keeps its place; it is matched by most of its words.
- **Files changed since you added them**: a card whose file is still there and no longer matches its fingerprint.
  Add it again to see what changed. `kb picture check` names these cards under its first question.
- **Where two cards that may be one project differ**: their kind or their last activity, with both sides and the
  file each came from. Neither side is taken as right.

Name one project to see only its versions: `kb picture changes "Corner bakery"`. The rules are old ones from
record-keeping: nothing is updated in place, a fact keeps when it was true and when it was learned, a file is
fingerprinted when it comes in, and a disagreement shows both sides in neutral words.

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

#### Keeping a key, so the page can use it

A key you export lasts until that terminal closes, and the page never sees it. `kb keys add` keeps it instead:

```bash
kb keys add gemini
```

It writes the provider's entry if your models file does not have it yet, asks for the key without showing it as you
paste, and keeps it in `~/.config/kb/keys.env` (or the file `KB_KEYS` names), which only you can read. The key never
goes in the repo folder, the models file, the run log or a page, and kb never prints it back. Every kb command fills
in a kept key that your terminal does not set, so a key you export still wins there; the page reads the file again
for every job, so there is nothing to restart. `kb keys` lists which paid models the page asks and why any other is
left out, `kb keys remove gemini` takes a key away, and `kb keys cap` shows or sets the page's daily cap.

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

#### The look, and your record

Every page kb draws (this one, the list on your phone, the town and the plant walk) wears one look, drawn like a
manga page: a title card with focus lines closing in on the title, panels in heavy ink frames with hard shadows,
each panel's name in a narration box in its corner, your own notes in speech balloons, and the buttons that act as
slanted plates. Gold is for what you have earned and the red seal for what you decide. It follows your system's
light or dark setting, uses only the fonts on your machine, and moves only if your system allows motion. On a
laptop the list is two columns like this page: the inbox in the wide one, runs and lessons beside it.

The advice page and the list on your phone carry a small record in the title card. It counts only what you did:

- A review is one model's answer you rated. Every five reviews is a level.
- A streak is the days in a row that hold a run you rated, counted to today or yesterday.
- Each model wears a rank, from how often you would act on its advice over every run you rated: S at 70% or more,
  A at 50%, B at 35%, C at 20%, D below that. A model with no rated run has no rank yet.

Nothing is scored for opening a page or for ticking more. The rank is the same share as the "So far" row of the
table at the bottom of the page, taken over every run you rated rather than the last twelve, and shown where you
read the model's answer.

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

#### Your inbox

The first box on the phone page is an inbox. Paste a post or a link into it, attach screenshots, PDFs, Word or
PowerPoint files and voice notes from the phone, or press **Record a voice note** and speak. **Send to kb** puts each
one in `work/inbox` on the laptop. A few words sent with files become their note; a longer text, or a link, is kept
as an item of its own. On the laptop you can drag files onto the box, or use the command line:

```bash
kb inbox                                   # everything you sent, newest first
kb inbox add ~/Downloads/call.pdf --note "for the bakery"
kb inbox show in_3f2a9c0d1b7e              # one item, with the text kb read from it
```

kb knows each file by its content, never by its name, and never opens or runs it. It reads what it can on the
laptop, at once: text and posts as they are, the text layer of a PDF page by page, and the words of a .docx or
.pptx file. A link (alone, or up to three inside a pasted post) is opened once by kb serve, the way a browser with scripts off would read it, and the page's title and words are kept beside it; the links you sent before are opened the next time kb serve starts. Only internet addresses are opened, never one on this laptop or your home network, up to 5 MB a page. A page behind a sign-in (LinkedIn, X and the like) shows only its wall: kb says so on the item, so paste the post's words or a screenshot instead. `kb inbox add` keeps a link as text only. Screenshots, scanned PDFs and voice notes are
kept whole and marked as waiting for an image or speech reader that runs on the laptop; none is built in yet.
Nothing is overwritten: the same file sent twice is kept once, and a second note on it goes beside the first.

What kb read goes into `work/inbox/text`, one file per item, so the scout can look for chances in it:

```bash
kb scout read work/inbox/text
```

A send can be up to 100 MB a file. Nothing in the inbox leaves the laptop, unless you run the scout with a model you
`--allow` for that run.

#### Share to kb from any app

On an Android phone, kb can sit in the Share menu of every app, beside WhatsApp and Gmail. Open kb's `.ts.net`
address in Chrome once, open the menu (the three dots) and press **Add to Home screen** (or **Install app**). From
then on, **Share** in any app lists **kb**: a post, a link, a screenshot, a PDF or a voice note opens kb's page with
it already in the inbox box. Add a few words if you like and press **Send to kb**; nothing reaches the laptop before
you press it.

The phone keeps what you shared in its own cache until the page picks it up, then deletes it. kb's laptop side never
reads a share by itself: a share that arrives before kb was opened on the phone is dropped, and the page asks you to
share again, so no other site can put anything in your inbox. iPhones do not offer this to web apps yet; there,
paste into the inbox box as before.

#### Without a terminal

The page has an **Ask kb** box, so the daily jobs need no commands:

- **Ask for advice** runs `kb picture advise` with every model you like, your private list and your lessons: the
  models on this laptop, and each paid model whose key kb keeps and whose price it knows, under your daily cap.
- **Find chances in my inbox** runs the scout on what kb read from your inbox.
- **Add cards from a file** merges the PROJECT CARDs in a file you pick, as `kb picture add` does: nothing is
  overwritten, and a copy of the file is kept in `work/cards`, so kb can say where each card came from.
- **Check my picture** and **See chances** show `kb picture check` and the open chances as pages.

Each button runs the very command you would type, as a separate process on the laptop, so every rule stays the same.
For advice the page passes `--allow` with the paid models it chose, and no others. Before it starts, it adds what
paid models cost today (from the run log) to what this run will likely cost: the most one advice run from that model
has cost so far, or before its first run the most it could cost. A paid model that would go over the cap waits for
tomorrow. The cap is `"daily_cap"` in the models file, $1 until you change it with `kb keys cap` and the dollars. A
model without a known price is left out, because kb cannot keep it under the cap; add `price_in` and `price_out`
(dollars per million tokens) to its entry. Lines that are private never go to a model off this laptop, as on the
command line. The scout asks once for every item in your inbox, so it stays on this laptop's models. The Ask kb box
shows which models a press would ask, what paid models cost today, and why any model is left out. One job runs at a
time; you can leave the page while it works, and it shows the result in one sentence when you come back.

To have the page there whenever you log in, without a terminal window, run once:

```bash
kb serve --install
```

It writes one small file, `~/.config/systemd/user/kb-serve.service`, and starts kb serve now and at every login. If an
older kb serve is still running in a terminal you can no longer find, it stops that one first. It
needs no sudo, runs as you, and still listens on `127.0.0.1` only. After you update kb, run `kb serve --install`
again so it starts the new version. `kb serve --uninstall` takes it away; if the page does not open, see why with
`journalctl --user -u kb-serve.service -n 30`.

#### Where you were

Work gets scattered: a chat in one AI, a search, a PDF in Downloads, notes in a folder. The **Where you were** box
on the page shows them together, newest first, since yesterday: your AI chats (Claude, ChatGPT, Gemini, Perplexity,
DeepSeek, Kimi and others), your searches, documents and research pages, the files you opened and the files you
changed. **See all and find a word** opens every day you choose (today, since yesterday, 7 or 30 days); type a word
from a lost chat or paper and only the lines with it stay. **Keep in inbox** puts a page (its title and address) or a
copy of a file into your inbox, so the scout and advice can build on it. In the terminal:

```bash
kb where --find "reverse engineering"
```

It is off until you press **Show where I was**. kb reads it fresh on the laptop each time, from what is already
there: the history file of Chrome, Chromium, Brave, Edge, Vivaldi, Opera, Firefox, Zen, LibreWolf or another
browser built on them, wherever it keeps it (snap, flatpak or its own folder; copied first, as the browser keeps it
locked), the desktop's list of files you opened, and the dates on the files in your home folder (hidden
folders, caches and code environments are skipped). It keeps none of it, sends none of it anywhere and shows none of
it to a model. Addresses lose the parts that look like keys (`token=`, `code=`, `key=` and the like) before they are
shown. **Stop showing where I was** turns it off again.

#### Where your work waits

Two small engines from operations research, worked out from your cards on the laptop. No model is asked, and nothing
leaves the machine. They show on the page under the inbox, and in the terminal:

```bash
kb picture engines
```

- **What frees the most.** Every need that is not met yet waits on someone or something, the third part of the need
  on the card. kb groups the needs by who they wait on, and for each one names the cards that would have nothing left
  waiting once that part is done. Cards that wait on one thing only are listed as **one step from free**, the card
  tied to most other cards first, because moving it moves the most.
- **How long things wait.** Little's law: what is open = how fast it closes × how long it waits. kb counts what is
  open now (needs not met, open decisions, unfinished work), reads how fast things close from the versions it keeps
  of your cards, and says how long a new one waits at that pace. When more open than close, the wait keeps growing:
  that is the warning. kb cannot tell done from dropped, so the pace is a sketch, and it shows only after two weeks
  of versions. **Quiet longest** lists the cards with open work that have not moved for the longest time.

The math comes from the research "Mathematical Engines of Plan→T", carried over from a plant to your own work.

#### Your books: the frame-outer

kb has a crew: what comes in is routed to the agent that owns it (`knowledgebreeder/picture/crew.py`, plain rules,
no model guessing). The first agent is the frame-outer. Give it a book title, in the Your books box, or as a line
`book: Algorithms to Live By` sent to the inbox, and it gives back four things:

1. the book's framework: its principles, each with what it says and how you would use it;
2. a platform of its own that would carry out the book's ideas;
3. features for the platforms on your cards, each naming the card and the principle it comes from (a platform that
   is not one of your cards is dropped);
4. a song: verses that carry the principles and a chorus with the book's big idea, so singing it brings them back.

It works from what the model knows of the book, not your clips, and says when it does not know a book. It asks the
first paid model under your daily cap (they know books best), else a model on this laptop, and sends only the title
and the name and first line of each card that is not private. The frames are kept in `work/books/`, and their lines
land in Your ideas, where you tick what rings true.

```
kb books add "Algorithms to Live By"
kb books frame --model kimi --allow kimi
kb books show "Algorithms to Live By"
```

#### kb updates itself, and a menu bar instead of a long scroll

The first page opens with a menu bar that names every box. Tap a name and the page shows just that box; **All** shows
them all again. kb remembers the last box you opened.

You no longer type `git pull`. `kb serve --install` also sets a nightly update (about 4 AM): it brings new kb code down
from GitHub and restarts kb serve on it. When new code lands sooner, the page shows **Update kb**; press it and the page
reloads on the new code. The page asks GitHub each time you open it (at most once a minute), so the button shows
up as soon as a pull request is merged. `kb update` does the same by hand. It only fast-forwards kb's own folder to GitHub's main: if
you changed kb's files yourself or the folder is on another branch, it stops and says so. Your cards, `work/` and keys
are never touched. After this pull request, run `kb serve --install` once to turn the nightly update on.

#### kb builds itself: Send to Claude

The kb grows from your cards box keeps kb's own build list. Send to Claude hands it to Claude on GitHub: kb opens one
issue in this repository with the lines not sent before and a request to `@claude`, and the workflow
`.github/workflows/claude.yml` answers it. Claude builds the lines on a branch and opens a pull request. Nothing
reaches kb until you merge it. Each line then shows its issue, and a second press sends only what was added since.

This repository is public, so the issue is public. A line that names anything on your private list, a card marked
#private, a phone, an email, a key or money stays on the laptop, and a card's name goes along only when the card may
leave. Only the repository's owner can start a build, so a stranger's issue spends nothing.

Once, to set it up:

1. On GitHub, install the Claude app on this repository: https://github.com/apps/claude
2. In the repository's Settings, Secrets and variables, Actions, add the secret `ANTHROPIC_API_KEY` (a Claude API
   key; builds are billed to it).
3. On the laptop, keep a GitHub key that may open issues here (Issues: Read and write, this repository only):

```
kb keys add github
```

#### Your ideas

One ledger of every idea, lesson, check and book principle kb has read, each with the file and line it came from.
It is the base the next parts stand on: the bookshelf, the forgot-checker and the matcher across projects. It reads
the ideas not started and the reusable parts on your cards, and the markdown files you add: a journey file, a "KB
thinks" file, or any file whose headings say lessons, strengths, weak spots, what you forgot, ideas or a book. Under
those headings each list line is one row. Timelines, sources and how-it-works sections are story and are left out.

Add a file with **Add cards from a file** on the page (a file with no cards in it is kept as ideas), by sending it to
your inbox, or in the terminal:

```bash
kb picture ideas --add stairs-journey.md smt-journey.md
kb picture ideas
```

Answer each row **Useful**, **Not now** or **Done**, oldest first, so what you may have forgotten comes back first.
Two numbers say whether kb's ideas help you: of the rows you answered in the last 7 days, how many were useful, and
how many you marked done in the last 30 days. Rows are worked out from their sources every time and never stored;
only your answers and the day kb first saw each row are kept, in `work/ideas.json`. The same line about the same
project keeps its answer when you send a newer copy of the file. No model reads anything here.

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
- `kb serve` runs while you are logged in to the laptop (after `kb serve --install`), or while its terminal is open.
  The phone reaches it only while the laptop is on and awake. Its safety rests on staying on `127.0.0.1`, with Tailscale as the only way in.
- The inbox reads text, links, PDFs with a text layer, and .docx and .pptx files. It does not yet read screenshots,
  scans or voice: those wait, kept whole, for a reader that runs on the laptop. It does not read .doc, .xls or
  .xlsx files, and a share from another app needs the page open (there is no share button into kb yet).
- `kb process` reads typed words only. Voice notes wait for a speech reader that runs on the laptop.
- `kb thoughts` joins thoughts by a model's reading and by shared words. It has not yet been run on a real inbox
  with a real model, and its "may help" joins are hints, not findings.
- No accuracy number is claimed for this repo yet. `breeding/scores.jsonl` will hold them as they are measured.

## Credits and licence

MIT. The seed skill is by Scott Duncan, MIT, kept unchanged with its licence; see [NOTICE.md](NOTICE.md).
