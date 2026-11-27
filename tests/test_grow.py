"""kb grows from your cards: kb's own card and the lines on other cards that name kb become kb's own to-do list."""

from __future__ import annotations

import json
import re
import threading
from datetime import date

import pytest
from test_explain import _boxes, _text
from test_serve import ask

from knowledgebreeder.picture import Picture, cards, grow, serve

TODAY = date(2026, 11, 25)

CARDS = """
### PROJECT CARD 1
name: KnowledgeBreeder
aliases: kb
one_line: A local tool that keeps the picture of your work.
area: Tools
kind: tool
last_activity: 2026-11-24
source: the owner's notes
WHAT IT NEEDS
- a reader for scanned receipts | no | a vision model
- a first run on the phone | yes | the owner
- ten rated runs | no | Tee
UNFINISHED
- the weekly order sheet from voice notes | not built | three real voice notes
IDEAS NOT STARTED
- a print view of the week
REUSABLE PARTS
- the card format | any bakery that keeps notes
OPEN DECISIONS: which reader to try first.

### PROJECT CARD 2
name: Saturday baking class
one_line: A weekend class for beginners.
area: Bakery
kind: class
last_activity: 2026-11-20
source: the owner's notes
IDEAS NOT STARTED
- let kb remind the class a day before
- a second class in spring
REUSABLE PARTS
- the sign-up sheet with a waiting list | kb could keep the same list for chances
- the oven timer | the kitchen only, and a 20 KB file
LINKS TO MY OTHER WORK
- KnowledgeBreeder | same owner, same notes
"""


def _pic():
    pic = Picture()
    pic.add(cards.parse(CARDS), recorded="2026-11-24")
    return pic


def test_kb_own_card_and_the_lines_that_name_kb_become_its_to_do():
    got = [(x["kind"], x["card"], x["what"], x["why"]) for x in grow.lines(_pic().cards)]
    assert got == [
        ("unfinished", "KnowledgeBreeder", "the weekly order sheet from voice notes", "not built · three real voice notes"),
        ("need", "KnowledgeBreeder", "a reader for scanned receipts", "a vision model"),
        ("decision", "KnowledgeBreeder", "which reader to try first.", ""),
        ("idea", "KnowledgeBreeder", "a print view of the week", ""),
        ("idea", "Saturday baking class", "let kb remind the class a day before", ""),
        ("part", "Saturday baking class", "the sign-up sheet with a waiting list", "kb could keep the same list for chances"),
    ]
    # a met need, a need on you, kb's own parts (what kb gives others), a link, and "20 KB" are not kb's to-do
    assert grow.names_kb("let kb remind") and grow.names_kb("KnowledgeBreeder's layer") and not grow.names_kb("a 20 KB file")
    assert grow.is_kb({"name": "Knowledge Breeder"}) and grow.is_kb({"name": "x", "aliases": ["kb"]})
    assert not grow.is_kb({"name": "kb notes for the bakery"})


def test_your_answers_are_kept_and_the_build_list_copies_out(tmp_path):
    items = grow.lines(_pic().cards)
    m = grow.Marks(tmp_path / "grow.json")
    m.set(items[0]["id"], "build", TODAY)
    m.set(items[4]["id"], "build", TODAY)
    m.set(items[1]["id"], "later", TODAY)
    m.set(items[2]["id"], "done", TODAY)
    m.set(items[2]["id"], "", TODAY)                                   # answered by mistake: back to new
    with pytest.raises(KeyError):
        m.set("../../etc", "build", TODAY)
    with pytest.raises(KeyError):
        m.set(items[0]["id"], "maybe", TODAY)
    groups = grow.sort(grow.lines(_pic().cards), grow.Marks(tmp_path / "grow.json").all())   # read again: still there
    assert [len(groups[k]) for k in ("build", "new", "later", "done")] == [2, 3, 1, 0]
    assert grow.build_text(groups["build"], "Build these:", "from").splitlines() == [
        "Build these:",
        "1. the weekly order sheet from voice notes (from KnowledgeBreeder: not built · three real voice notes)",
        "2. let kb remind the class a day before (from Saturday baking class)",
    ]


def test_the_page_lets_you_answer_each_line_and_copy_the_build_list(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        box = _boxes(ask(kb, "GET", "/")[2])["grow"]
        assert "To build (0)" in box and "New from your cards (6)" in box and 'id="g-copy"' not in box
        assert box.count('data-state="build"') == 6 and "See all 6 new lines" in box
        first = re.search(r'data-id="([0-9a-f]{12})" data-state="build"', box)[1]
        code, _, out = ask(kb, "POST", "/api/grow", {"id": first, "state": "build"})
        assert code == 200 and json.loads(out)["ok"] is True
        assert ask(kb, "POST", "/api/grow", {"id": first, "state": "soon"})[0] == 400
        doc = ask(kb, "GET", "/")[2]
        box = _boxes(doc)["grow"]
        assert "To build (1)" in box and 'id="g-copy"' in box
        text = _text(box.split('id="g-text"', 1)[1].split("</textarea>")[0].split(">", 1)[1])
        assert text.startswith("Build these into KnowledgeBreeder (kb). They come from my cards: 1. the weekly order")
        bubble = box.split('<div class="ex-body">', 1)[1].split("</details>", 1)[0]
        told = {_text(x) for x in re.findall(r"<dt>(.*?)</dt>", bubble)}
        assert {_text(x) for x in re.findall(r"<button[^>]*>(.*?)</button>", box.replace(bubble, ""))} <= told
        ask(kb, "POST", "/api/grow", {"id": first, "state": "done"})
        box = re.sub("[\u2068\u2069]", "", _boxes(ask(kb, "GET", "/?lang=ar")[2])["grow"])     # without the isolates
        assert "للبناء (0)" in box and "تم: 1." in box and "ابنِ هذا" in box
    finally:
        srv.shutdown()
        srv.server_close()


def test_send_to_claude_opens_one_public_issue_without_anything_private(tmp_path):
    from knowledgebreeder import keys
    from knowledgebreeder.picture import handoff
    w = tmp_path / "w"
    w.mkdir()
    _pic().save(w / "picture.json")
    (w / "private.md").write_text("- Saturday baking class\n- scanned receipts\n")   # a card's name and a line's words
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    posts: list[tuple[str, str, dict]] = []

    def fake(url, token, payload):
        posts.append((url, token, payload))
        return {"number": 7, "html_url": "https://github.com/TamerMomtaz/KnowledgeBreeder/issues/7"}
    kb.handoff_post = fake
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        items = grow.lines(_pic().cards)
        for i in (0, 1, 4):               # kb's unfinished line, a private need, and a line from the private card
            kb.grow_marks.set(items[i]["id"], "build", TODAY)
        box = _boxes(ask(kb, "GET", "/")[2])["grow"]
        assert 'id="g-send"' in box and "Send to Claude" in box and "public" in _text(box)
        code, _, out = ask(kb, "POST", "/api/handoff", {"lang": "en"})
        assert code == 400 and "kb keys add github" in json.loads(out)["error"] and not posts
        keys.put(handoff.KEY, "github_pat_0123456789abcdef")
        code, _, out = ask(kb, "POST", "/api/handoff", {"lang": "en"})
        got = json.loads(out)
        assert code == 200 and got["number"] == 7 and got["sent"] == 2 and got["held"] == 1
        assert "issue #7" in got["say"] and "stayed here" in got["say"]
        url, token, payload = posts[0]
        assert url.endswith("/repos/TamerMomtaz/KnowledgeBreeder/issues") and token.startswith("github_pat_")
        assert payload["body"].startswith("@claude please build") and payload["title"].startswith("kb build: ")
        assert "the weekly order sheet" in payload["body"] and "let kb remind the class" in payload["body"]
        assert "Saturday baking class" not in json.dumps(payload) and "receipts" not in json.dumps(payload)
        assert "(from one of my cards)" in payload["body"]
        assert "github_pat" not in json.dumps(payload)
        code, _, out = ask(kb, "POST", "/api/handoff", {"lang": "en"})        # nothing new: nothing sent again
        got = json.loads(out)
        assert code == 200 and got["sent"] == 0 and got["held"] == 1 and "private" in got["say"] and len(posts) == 1
        box = _boxes(ask(kb, "GET", "/")[2])["grow"]
        assert box.count("sent to Claude, issue #7") == 2 and 'href="https://github.com/' in box
        bubble = box.split('<div class="ex-body">', 1)[1].split("</details>", 1)[0]
        told = {_text(x) for x in re.findall(r"<dt>(.*?)</dt>", bubble)}
        assert {_text(x) for x in re.findall(r"<button[^>]*>(.*?)</button>", box.replace(bubble, ""))} <= told
        ar = re.sub("[\u2068\u2069]", "", _boxes(ask(kb, "GET", "/?lang=ar")[2])["grow"])
        assert "أرسلها إلى Claude" in ar
    finally:
        srv.shutdown()
        srv.server_close()


def test_kb_keys_add_github_keeps_the_key_without_showing_it(tmp_path, monkeypatch, capsys):
    import getpass

    from knowledgebreeder import keys
    from knowledgebreeder.cli import main
    from knowledgebreeder.picture import handoff
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "github_pat_0123456789abcdef")
    assert main(["keys", "add", "github", "--models-file", str(tmp_path / "models.json")]) == 0
    out = capsys.readouterr().out
    assert "Issues, Read and write" in out and "github_pat" not in out
    assert keys.load()[handoff.KEY] == "github_pat_0123456789abcdef"


def test_kb_keys_add_github_refuses_a_claude_key(tmp_path, monkeypatch, capsys):
    import getpass

    from knowledgebreeder import keys
    from knowledgebreeder.cli import main
    from knowledgebreeder.picture import handoff
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "sk-ant-api03-0123456789abcdef")
    assert main(["keys", "add", "github", "--models-file", str(tmp_path / "models.json")]) != 0
    err = capsys.readouterr().err
    assert "Claude key" in err and "ANTHROPIC_API_KEY" in err and "sk-ant" not in err
    assert handoff.KEY not in keys.load()
