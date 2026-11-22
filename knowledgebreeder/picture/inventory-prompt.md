# The inventory prompt

A card is what one project says about itself. This prompt makes any assistant that holds a project (a chat, a
notebook, a coding session) write one, on any platform. Paste the block below into each project. Save each answer
in a text file, one file or many, then add them:

```bash
kb picture add my-cards.md
```

You can also write a card by hand for anything that lives in no tool at all: a craft, a habit, a plan.
Keep the headings exactly as they are. Write "unknown" where you do not know. The gaps are part of what the
picture is for.

```text
I am building one map of everything I work on, across many separate projects and tools, so I can see what is duplicated, what is missing, what is half finished, and what one project could give another. You are one of those projects. I need you to describe this project as a card that will be merged with cards from my other projects.

Use only what you actually know from this project: its files, its code, its documents, its instructions, its memory and our past conversations here. Look through them before you answer. Do not guess and do not fill gaps with what seems likely. Where you do not know, write "unknown". A card with honest gaps is more useful to me than a complete-looking one, because the gaps are part of what I am trying to find.

Write plainly, in short phrases. Name things the way I name them in this project. Leave out passwords, keys, tokens and private details about other people.

Reply with only the card below, inside one code block, keeping the headings exactly as written so the cards can be merged by a program.

PROJECT CARD
name: 
one_line: (what it is, in one sentence a stranger would understand)
area: (the part of my life or work it belongs to, e.g. software platform, music, painting, industrial plant, personal, business)
kind: (running product / being built / paused / idea only / finished / other)
last_activity: (date or rough period of the most recent real work, or unknown)
source: (which tool or platform this card comes from, and what you could see: code, documents, chat only)
owner: (who keeps these facts true, when that is someone other than me, such as a client; else leave it empty)

PURPOSE
problem: (what it is for)
who_it_serves: (the people or groups it is meant for)
my_goal: (what I have said I want from it)

WHAT EXISTS (things already made; one per line)
- name | type (code, document, design, data, song, artwork, method, model, other) | where it lives | state (working / partial / draft)

WHAT IT CAN DO (capabilities that work today; one per line, each starting with a verb)
- 

WHAT IT NEEDS (things it depends on or is waiting for: skills, tools, data, content, people, money, time, decisions; one per line)
- need | is it met today? (yes / partly / no) | by what

UNFINISHED (started and not completed; one per line)
- what | how far it got | what stopped it, if known

IDEAS NOT STARTED (things I mentioned wanting that were never begun; one per line)
- 

REUSABLE PARTS (anything here that could be useful outside this project; one per line)
- what | why it could travel

LINKS TO MY OTHER WORK (other projects, platforms or activities of mine named anywhere in this project; one per line)
- other thing | how it relates (uses, feeds, copies, depends on, competes with, same idea as)

RECURRING THEMES (ideas, values or methods I keep returning to in this project; up to five)
- 

OPEN DECISIONS (choices waiting on me; one per line)
- 

WHAT YOU COULD NOT SEE (parts of the project you had no access to, or questions above you could not answer and why)
- 
```
