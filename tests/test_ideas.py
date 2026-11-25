"""Your ideas: one ledger of every idea, lesson, check and book principle kb has read, each with its source."""

from __future__ import annotations

import json
import re
import threading
from datetime import date, timedelta

from test_explain import _boxes, _text
from test_grow import _pic
from test_serve import ask

from knowledgebreeder.cli import main
from knowledgebreeder.picture import ideas, serve

TODAY = date(2026, 11, 25)

JOURNEY = """# JOURNEY: The bakery app

card: The bakery app (card 3)
made: 2026-11-25

## In one minute

The app took orders by voice. This paragraph is story, not an idea.

## Timeline

- 2026-03-01: the first order came in by voice. [notes]

## Strengths

- Orders arrive by voice, so the baker never types.

## Weak spots

- The night list was printed twice and nobody noticed.

## Lessons (the morals)

1. **Say what happened.** A button that works and says nothing makes people press it twice.
2. Keep one list of orders, not two.

## What kb should keep an eye on

- The backup of the order list has never been restored once.

## Sources

- notes.md, orders.csv
"""

THINKS = """# KB thinks: the bakery app

## 1. Where the book resonates (Algorithms to Live By)

**1.1 Networking chapter: no acknowledgement means no message.** The printer never says it printed.
- Build: count a list as printed only when the printer answers.

## 2. Ideas that get stronger together

**2.1 One list, two faces.** The class sign-up and the orders could share one list.

## 4. Reverse-algorithm: how you build

1. Start from paper. This is a step of a story, not an idea to answer.
"""


def test_a_journey_file_gives_lessons_checks_strengths_and_weak_spots_with_their_line():
    rows = ideas.parse(JOURNEY, "bakery-journey.md")
    kinds = [r["kind"] for r in rows]
    assert kinds == ["strength", "weak", "lesson", "lesson", "check"]
    assert all(r["project"] == "The bakery app" for r in rows)
    first_lesson = rows[2]
    assert first_lesson["text"].startswith("Say what happened. A button that works")
    assert first_lesson["source"] == "bakery-journey.md:24 · Lessons (the morals)"
    assert not any("story" in r["text"] or "2026-03-01" in r["text"] or "orders.csv" in r["text"] for r in rows)


def test_a_kb_thinks_file_gives_book_lines_and_ideas_and_lines_under_a_title_carry_it():
    rows = ideas.parse(THINKS, "kb-thinks-bakery.md")
    assert [r["kind"] for r in rows] == ["principle", "principle", "idea"]
    assert rows[1]["text"].startswith("1.1 Networking chapter: no acknowledgement means no message: Build: count")
    assert rows[0]["project"] == "the bakery app"
    assert not any("Start from paper" in r["text"] for r in rows)


def test_cards_give_their_ideas_and_parts_and_each_row_is_kept_once(tmp_path):
    folder = tmp_path / "ideas"
    assert ideas.keep_file(folder, "bakery-journey.md", JOURNEY)["rows"] == 5
    assert ideas.keep_file(folder, "bakery-journey.md", JOURNEY)["kept"].endswith("bakery-journey.md")   # same file
    assert ideas.keep_file(folder, "bakery-journey.md", JOURNEY + "\n")["kept"].endswith("bakery-journey~2.md")
    assert ideas.keep_file(folder, "notes.md", "just a note, no lists")["rows"] == 0
    rows = ideas.ledger(_pic().cards, folder)
    assert len(rows) == len({r["id"] for r in rows}) == 5 + 6            # the copy adds nothing new
    assert rows[0]["kind"] == "check"                                    # what you may have forgotten comes first
    assert {r["source"] for r in rows if r["kind"] == "part"} == {"card KnowledgeBreeder", "card Saturday baking class"}


def test_answers_are_kept_and_the_two_numbers_say_whether_it_helps(tmp_path):
    rows = ideas.parse(JOURNEY, "j.md")
    book = ideas.Book(tmp_path / "ideas.json")
    v = ideas.view(rows, book, TODAY - timedelta(days=40))               # first seen 40 days ago
    assert v["new"] == 5 and v["numbers"]["useful_share"] is None
    book.mark(rows[0]["id"], "useful", TODAY)
    book.mark(rows[1]["id"], "later", TODAY)
    book.mark(rows[2]["id"], "done", TODAY - timedelta(days=3))
    book.mark(rows[3]["id"], "done", TODAY - timedelta(days=45))         # too old for either number
    v = ideas.view(ideas.parse(JOURNEY, "j.md"), book, TODAY)
    assert v["numbers"] == {"answered_7d": 3, "useful_7d": 2, "useful_share": 0.67, "done_30d": 1}
    assert v["new"] == 1 and v["to_answer"][0]["seen"] == (TODAY - timedelta(days=40)).isoformat()
    assert [r["id"] for r in v["useful"]] == [rows[0]["id"]]
    for bad in (("nothex", "useful"), (rows[0]["id"], "soon")):
        try:
            book.mark(*bad, TODAY)
            raise AssertionError("should refuse")
        except KeyError:
            pass


def test_the_page_shows_your_ideas_and_a_file_without_cards_is_kept_as_ideas(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        box = _boxes(ask(kb, "GET", "/")[2])["ideas"]
        assert "6 rows from 2 projects and files." in _text(box) and "Nothing answered in the last 7 days" in box
        code, _, out = ask(kb, "POST", "/api/cards", {"name": "bakery-journey.md", "text": JOURNEY, "lang": "en"})
        said = json.loads(out)
        assert code == 200 and said["say"] == "Kept 5 ideas from bakery-journey.md." and said["link"] == "#ideas"
        assert (w / "ideas" / "bakery-journey.md").exists()
        box = _boxes(ask(kb, "GET", "/")[2])["ideas"]
        assert "11 rows" in _text(box) and "bakery-journey.md:" in box
        first = re.search(r'data-id="([0-9a-f]{12})" data-state="useful"', box)[1]
        assert ask(kb, "POST", "/api/ideas", {"id": first, "state": "useful"})[0] == 200
        assert ask(kb, "POST", "/api/ideas", {"id": first, "state": "soon"})[0] == 400
        box = _boxes(ask(kb, "GET", "/")[2])["ideas"]
        assert "Last 7 days: 1 of 1 answered were useful." in _text(box) and "Useful (1)" in box
        bubble = box.split('<div class="ex-body">', 1)[1].split("</details>", 1)[0]
        told = {_text(x) for x in re.findall(r"<dt>(.*?)</dt>", bubble)}
        assert {_text(x) for x in re.findall(r"<button[^>]*>(.*?)</button>", box.replace(bubble, ""))} <= told
        box = re.sub("[⁨⁩]", "", _boxes(ask(kb, "GET", "/?lang=ar")[2])["ideas"])
        assert "أفكارك" in box and "مفيد" in box
    finally:
        srv.shutdown()
        srv.server_close()


def test_kb_picture_ideas_adds_files_answers_and_prints_a_real_example(tmp_path, capsys):
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    j = tmp_path / "bakery-journey.md"
    j.write_text(JOURNEY, encoding="utf-8")
    pf = str(w / "picture.json")
    assert main(["picture", "--file", pf, "ideas", "--add", str(j), "--today", TODAY.isoformat()]) == 0
    out = capsys.readouterr().out
    assert "bakery-journey.md: 5 ideas" in out and "Your ideas: 11 rows." in out
    row = re.search(r"--mark ([0-9a-f]{12}) useful", out)[1]                # a real row, never a placeholder
    assert main(["picture", "--file", pf, "ideas", "--mark", row, "done", "--json", "--today", TODAY.isoformat()]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["done"] == 1 and got["numbers"]["done_30d"] == 1
