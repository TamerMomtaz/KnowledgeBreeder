"""What you send to the inbox is read into your map of thoughts by the model on this laptop, and the page says so."""

from __future__ import annotations

import json
import threading
from datetime import date

from test_serve import ask

from knowledgebreeder.picture import serve
from knowledgebreeder.thoughts import store as tk

DAY = date(2026, 11, 28)


def _kb(tmp_path, here=("local",)):
    w = tmp_path / "w"
    w.mkdir(parents=True)
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=DAY)
    real = kb.chosen
    kb.chosen = lambda: {**real(), "here": list(here), "paid": [], "problem": None if here else "no models file"}
    return kb


def _reader(kb, calls, item_id, fail=None):
    """A stand-in for kb thoughts read: the first round reads the item into the map, the next finds nothing."""
    def run(argv):
        calls.append(argv)
        if fail:
            return 0, json.dumps([{"source": "inbox:" + item_id, "status": "failed", "error": fail}]), ""
        m = tk.Map(kb.map_file)
        if m.sources.get("inbox:" + item_id, {}).get("status") == "read":
            return 0, "[]", ""
        m.add_source("card:x", kind="card", title="A card")
        old, _ = m.add_thought("Plants run on clear hand-offs.", "infrastructure", "My projects", "card:x", "A card",
                               DAY, "rules")
        m.add_source("inbox:" + item_id, kind="inbox", title="post", ref=item_id, status="read", subject="Operations",
                     read={"on": DAY.isoformat(), "kept": 2})
        a, _ = m.add_thought("SOPs get work out of heads.", "utility", "Operations", "inbox:" + item_id, "post", DAY,
                             "model:local")
        b, _ = m.add_thought("Find where work gets stuck.", "need", "Operations", "inbox:" + item_id, "post", DAY,
                             "model:local")
        m.add_link(a, old, "needs", "model:local", DAY, "both are about hand-offs")
        m.add_link(a, b, "causes", "model:local", DAY)
        m.save()
        return 0, json.dumps([{"source": "inbox:" + item_id, "status": "read"}]), ""
    return run


def test_what_you_send_is_read_into_your_map_and_the_inbox_line_says_so(tmp_path):
    kb = _kb(tmp_path)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code, _, out = ask(kb, "POST", "/api/inbox", {"text": "Get processes out of people's heads and into SOPs. " * 3})
        assert code == 200 and kb.map_wake.is_set()          # sending wakes the reader
        item = json.loads(out)
        iid = item.get("id") or kb.inbox.items()[0]["id"]
        assert "reads it into your map soon" in ask(kb, "GET", "/")[2]
        calls = []
        kb.map_run = _reader(kb, calls, iid)
        got = kb.read_into_map()
        assert got["read"] == 1 and got["running"] is False and len(calls) == 2
        argv = calls[0]
        assert argv[argv.index("thoughts") + 1] == "read" and argv[argv.index("--model") + 1] == "local"
        assert "--allow" not in argv                         # only the model on this laptop reads: nothing leaves
        doc = ask(kb, "GET", "/")[2]
        assert "In your map: 2 thoughts in “Operations”, 1 links to what you had." in doc
        ar = ask(kb, "GET", "/?lang=ar")[2]
        assert "في خريطتك: \u20682\u2069 فكرة" in ar
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_inbox_line_says_why_an_item_is_not_in_your_map(tmp_path):
    kb = _kb(tmp_path)
    item = kb.inbox.add(b"A note worth keeping about suppliers and spend.", "note.txt", today=DAY)
    kb.map_run = _reader(kb, [], item["id"], fail="the model on this laptop did not answer")
    kb.read_into_map()
    line = serve.inbox_html(kb.inbox.items(), "en", mapped=kb.mapped())
    assert "Not read into your map yet: the model on this laptop did not answer" in line
    kb2 = _kb(tmp_path / "two", here=())
    kb2.inbox.add(b"Another note.", "n.txt", today=DAY)
    assert kb2.read_into_map()["problem"] == "no models file"
    assert "no model on this laptop (no models file)" in serve.inbox_html(kb2.inbox.items(), "en", mapped=kb2.mapped())


def test_a_command_that_fails_stops_the_round_and_says_why(tmp_path):
    kb = _kb(tmp_path)
    kb.inbox.add(b"Something to read.", "s.txt", today=DAY)
    calls = []

    def broken(argv):
        calls.append(argv)
        return 1, "", "error: the local model is not running"
    kb.map_run = broken
    got = kb.read_into_map()
    assert len(calls) == 1 and got["problem"] == "the local model is not running"
