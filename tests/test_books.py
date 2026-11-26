"""kb's crew: the router hands book titles to the frame-outer, which turns each into a framework, a platform of its
own, features for the platforms on your cards, and a song. Everything lands in Your ideas."""

from __future__ import annotations

import json
import threading
from datetime import date

from test_explain import _boxes, _text
from test_grow import _pic
from test_serve import ask

from knowledgebreeder import keys, models
from knowledgebreeder.cli import main
from knowledgebreeder.models import config
from knowledgebreeder.picture import actions, books, crew, ideas, serve
from knowledgebreeder.picture.private import Private

TODAY = date(2026, 11, 26)
REPLY = {
    "known": True, "author": "A. Baker",
    "framework": [{"name": "Rest the dough", "says": "Time does the work kneading cannot.",
                   "use": "Give each batch a fixed rest before shaping."},
                  {"name": "Weigh, do not guess", "says": "Grams beat cups.", "use": "Put a scale in every recipe."}],
    "platform": {"name": "RiseClock", "what": "Tells each baker when the dough is ready.",
                 "how": ["A timer per batch", "A note when it is ready"], "principles": ["Rest the dough"]},
    "features": [{"platform": "Saturday baking class", "feature": "A rest timer on each lesson",
                  "principle": "Rest the dough", "why": "Beginners cut the rest short."},
                 {"platform": "A platform that is not a card", "feature": "x", "principle": "y", "why": "z"}],
    "song": {"title": "Let it rise", "lyrics": "Weigh the flour, not the cup\\nRest the dough and let it up"},
    "unsure": "The chapter on ovens.",
}


def test_the_router_finds_book_lines_and_the_list_under_books():
    t = "book: Algorithms to Live By\nSome note\n📖 Range\nBooks:\n- Deep Work\n2. The Goal\n\nnot a book\nكتاب: فن الحرب"
    assert crew.books_in(t) == ["Algorithms to Live By", "Range", "Deep Work", "The Goal", "فن الحرب"]
    assert crew.route("just a post about bread https://example.org") == {}
    assert crew.route("Book - Deep Work")["frame-outer"] == ["Deep Work"]


def test_a_reply_is_checked_and_a_feature_for_a_platform_you_do_not_have_is_dropped():
    plats = [("Saturday baking class", "A class on Saturdays"), ("KnowledgeBreeder", "kb")]
    f = books.check(REPLY, plats)
    assert f["known"] and len(f["framework"]) == 2 and f["dropped_features"] == 1
    assert [x["platform"] for x in f["features"]] == ["Saturday baking class"]
    assert f["song"]["lyrics"].splitlines() == ["Weigh the flour, not the cup", "Rest the dough and let it up"]
    unknown = books.check({"known": False, "framework": [{"name": "made up"}]}, plats)
    assert not unknown["known"] and unknown["framework"] == [] and unknown["song"]["lyrics"] == ""


def test_only_cards_that_may_leave_the_laptop_are_named_to_the_model():
    cards = {"a": {"name": "Saturday baking class", "one_line": "A class on Saturdays"},
             "b": {"name": "Dar Bakery", "one_line": "a client"},
             "c": {"name": "Secret thing", "one_line": "#private"}}
    plats, held = books.platforms(cards, Private(["Dar Bakery"]))
    assert plats == [("Saturday baking class", "A class on Saturdays")] and held == 2
    system, user = books.prompt("The Bread Book", plats, "ar")
    assert "Egyptian Arabic" in system and "Saturday baking class" in user and "Dar Bakery" not in user


def test_framing_a_book_keeps_the_frame_and_puts_its_lines_in_your_ideas(tmp_path, monkeypatch):
    shelf = books.Shelf(tmp_path / "books")
    assert shelf.add(["The Bread Book", "The Bread Book", "Unknown Book"], TODAY) == ["The Bread Book", "Unknown Book"]
    answers = {"The Bread Book": REPLY, "Unknown Book": {"known": False}}

    def fake(m, system, user, allow=(), sending=""):
        title = user.split("\n", 1)[0].removeprefix("The book: ")
        return answers[title], models.Answer(text="{}", worker=m.name, model=m.model, host="x", where="outside", ms=5,
                                             tokens_in=1000, tokens_out=500, cost=0.014, chars_sent=len(user))
    monkeypatch.setattr(books.models, "ask_json", fake)
    m = config.Model("kimi", "openai", "https://api.moonshot.ai/v1", "kimi-k3.1-pro", key_env="MOONSHOT_API_KEY")
    r = books.frame_waiting(shelf, tmp_path / "ideas", _pic().cards, m, Private(), TODAY, allow=["kimi"])
    assert [b["status"] for b in r["books"]] == ["framed", "framed"] and r["left"] == 0
    assert r["books"][1]["known"] is False and r["books"][1]["ideas"] == 0
    rows = ideas.ledger({}, tmp_path / "ideas")
    kinds = sorted(x["kind"] for x in rows)
    assert kinds == ["check", "idea", "idea", "principle", "principle"]                # no lyric is a row
    assert {x["project"] for x in rows} == {"The Bread Book"}
    page = (tmp_path / "books" / "the-bread-book.md").read_text()
    assert "## The song: Let it rise" in page and "not your clips" in page
    assert shelf.read()["the-bread-book"]["status"] == "framed"


def _kb(tmp_path, runner):
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    config.add_preset(w / "models.json", "kimi")
    keys.put("MOONSHOT_API_KEY", "sk-test-0123456789abcdef")
    return serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY, jobs=actions.Jobs(runner=runner)), w


def test_the_page_frames_titles_with_the_paid_model_and_the_inbox_routes_book_lines(tmp_path):
    seen: list[list[str]] = []
    result = {"books": [{"title": "The Bread Book", "status": "framed", "known": True, "ideas": 5}], "left": 0}

    def runner(argv):
        seen.append([str(x) for x in argv])
        return 0, json.dumps(result), ""
    kb, w = _kb(tmp_path, runner)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        box = _boxes(ask(kb, "GET", "/")[2])["books"]
        assert "It frames with kimi." in _text(box) and "No books yet" in _text(box)
        assert ask(kb, "POST", "/api/books", {"titles": "  ", "lang": "en"})[0] == 400
        code, _, out = ask(kb, "POST", "/api/books", {"titles": "The Bread Book\nThe Goal", "lang": "en"})
        assert code == 200 and json.loads(out)["added"] == 2
        kb.jobs.wait()
        argv = seen[-1]
        assert argv[argv.index("--model") + 1] == "kimi" and argv[argv.index("--allow") + 1] == "kimi"
        assert "frame" in argv and str(w / "books") in argv
        assert serve.job_say(kb.jobs.state(), "en")["say"] == "Framed: 1. Their lines are in Your ideas."
        code, _, out = ask(kb, "POST", "/api/inbox", {"text": "book: Range\nfor the DBA"})
        assert code == 200 and json.loads(out)["books"] == 1
        assert "Range" in [v["title"] for v in kb.shelf.read().values()]
        box = _boxes(ask(kb, "GET", "/?books=1")[2])
        assert "Books: 1, sent to the frame-outer" in _text(box["inbox"])
        assert "Range" in _text(box["books"])
        ar = _boxes(ask(kb, "GET", "/?lang=ar")[2])["books"]
        assert "كتبك" in ar
    finally:
        srv.shutdown()
        srv.server_close()


def test_kb_books_add_and_frame_from_the_terminal(tmp_path, monkeypatch, capsys):
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    config.add_preset(w / "models.json", "kimi")
    monkeypatch.setattr(books.models, "ask_json", lambda m, s, u, allow=(), sending="": (REPLY, models.Answer(
        text="{}", worker=m.name, model=m.model, host="x", where="outside", ms=5, tokens_in=10, tokens_out=10,
        cost=0.001, chars_sent=10)))
    common = ["--books", str(w / "books"), "--today", TODAY.isoformat()]
    assert main(["books", "add", "The Bread Book", *common]) == 0
    assert "On the shelf: 1 new" in capsys.readouterr().out
    assert main(["books", "frame", *common, "--file", str(w / "picture.json"), "--models-file", str(w / "models.json"),
                 "--runlog", str(w / "runs.db"), "--model", "kimi", "--allow", "kimi"]) == 0
    out = capsys.readouterr().out
    assert "The Bread Book: framed." in out and "features for your platforms" in out
    assert main(["books", "show", "The Bread Book", *common]) == 0
    assert "RiseClock" in capsys.readouterr().out
    assert (w / "ideas").is_dir() and any((w / "ideas").glob("book-*.md"))
