"""Reminders on your phone: a morning note and deadline reminders through ntfy, off until you turn them on."""

from __future__ import annotations

import json
import os
import re
import stat
import threading
import urllib.error
from datetime import date, datetime

from test_serve import ask
from test_soon import CARDS, TODAY

from knowledgebreeder.picture import Picture, cards, nudge, serve, soon
from knowledgebreeder.picture.private import Private


def _cards():
    return {c["name"]: c for c in cards.parse(CARDS)}


class Phone:
    """Stands in for ntfy: keeps what kb would have sent."""

    def __init__(self, fail: bool = False):
        self.got, self.fail = [], fail

    def __call__(self, url, body, headers):
        if self.fail:
            raise urllib.error.URLError("no network")
        assert url == "https://ntfy.sh/" and headers == {"Content-Type": "application/json"}
        self.got.append(json.loads(body.decode("utf-8")))


def test_nothing_goes_while_off_and_the_topic_is_long_random_and_kept(tmp_path):
    n, phone = nudge.Nudge(tmp_path / "nudge.json"), Phone()
    assert n.tick(datetime(2026, 11, 25, 9), soon.coming(_cards(), TODAY), None, Private(), post=phone) == []
    assert phone.got == [] and not (tmp_path / "nudge.json").exists()
    topic = n.turn(True)["topic"]
    assert re.fullmatch(r"kb-[A-Za-z0-9]{32}", topic)
    assert stat.S_IMODE(os.stat(tmp_path / "nudge.json").st_mode) == 0o600
    assert nudge.Nudge(tmp_path / "other.json").turn(True)["topic"] != topic
    n.turn(False)
    assert n.turn(True)["topic"] == topic                  # the phone keeps listening to the same topic


def test_the_morning_note_goes_once_a_day_and_nothing_at_night(tmp_path):
    n, phone = nudge.Nudge(tmp_path / "nudge.json"), Phone()
    n.turn(True)
    rows = soon.coming(_cards(), TODAY)
    assert n.tick(datetime(2026, 11, 25, 7, 30), rows, None, Private(), post=phone) == []
    assert n.tick(datetime(2026, 11, 25, 9, 0), rows, None, Private(), post=phone) == ["morning:2026-11-25"]
    note = phone.got[0]
    assert note["title"] == "kb · good morning" and note["priority"] == 3 and note["topic"] == n.state()["topic"]
    assert note["message"].splitlines() == [
        "Coming up:",
        "• Saturday baking class: the class flyer (in 3 days, 28/11)",
        "• Delivery bike: the city permit, no later than 2026-11-30 (in 5 days, 30/11)",
        "• Saturday baking class: whether to open a second class by December 1, 2026. (in 6 days, 1/12)",
        "Slipped and still open:",
        '• Saturday baking class: a food-safety certificate ("before 31 October 2026") (25 days ago, 31/10)',
    ]
    assert n.tick(datetime(2026, 11, 25, 9, 5), rows, None, Private(), post=phone) == []
    assert n.tick(datetime(2026, 11, 26, 15, 0), rows, None, Private(), post=phone) == []   # too late for a morning note
    later = soon.coming(_cards(), date(2026, 11, 27))
    assert n.tick(datetime(2026, 11, 27, 23, 0), later, None, Private(), post=phone) == []  # night
    sent = n.tick(datetime(2026, 11, 27, 10, 0), later, None, Private(), post=phone)
    assert sent[0] == "morning:2026-11-27" and sent[1].startswith("due:Saturday baking class:2026-11-28:1:")
    due = phone.got[-1]
    assert due["title"] == "Due tomorrow" and due["priority"] == 4 and due["message"] == "Saturday baking class: the class flyer"
    assert n.tick(datetime(2026, 11, 27, 18, 0), later, None, Private(), post=phone) == []  # once


def test_private_lines_are_cut_down_before_they_leave(tmp_path):
    n, phone = nudge.Nudge(tmp_path / "nudge.json"), Phone()
    n.turn(True)
    rows = soon.coming(_cards(), date(2026, 11, 27))
    n.tick(datetime(2026, 11, 27, 9), rows, None, Private(["flyer", "Delivery bike"]), post=phone)
    said = "\n".join(x["message"] for x in phone.got)
    assert "flyer" not in said and "Delivery bike" not in said
    assert "Saturday baking class: a private item" in said
    assert "the city permit, no later than 2026-11-30" in said      # the line stays; the card's name does not


def test_a_failed_send_is_kept_and_tried_again(tmp_path):
    n = nudge.Nudge(tmp_path / "nudge.json")
    n.turn(True)
    rows = soon.coming(_cards(), TODAY)
    assert n.tick(datetime(2026, 11, 25, 9), rows, None, Private(), post=Phone(fail=True)) == []
    assert "URLError" in n.state()["error"] and n.state()["sent"] == {}
    phone = Phone()
    assert n.tick(datetime(2026, 11, 25, 9, 5), rows, None, Private(), post=phone) == ["morning:2026-11-25"]
    assert n.state()["error"] == "" and n.state()["last"] == "2026-11-25 09:05 kb · good morning"


def test_the_page_turns_reminders_on_tests_them_and_turns_them_off(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    pic = Picture()
    pic.add(cards.parse(CARDS), recorded="2026-11-24")
    pic.save(w / "picture.json")
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    kb.nudge_post = phone = Phone()
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        _, _, doc = ask(kb, "GET", "/")
        box = doc.split('id="nudge"')[1].split("</section>")[0]
        assert 'id="nudge-on"' in box and "Turn on phone reminders" in box and "ntfy://" not in box
        code, _, out = ask(kb, "POST", "/api/nudge", {"do": "test"})
        assert code == 400 and "Turn phone reminders on first." in out
        code, _, out = ask(kb, "POST", "/api/nudge", {"do": "on", "lang": "ar"})
        assert code == 200 and json.loads(out)["on"] is True
        topic = kb.nudge.state()["topic"]
        _, _, doc = ask(kb, "GET", "/")
        box = doc.split('id="nudge"')[1].split("</section>")[0]
        assert f'href="ntfy://ntfy.sh/{topic}?display=kb"' in box and f'<code dir="ltr">{topic}</code>' in box
        assert 'id="nudge-test"' in box and 'id="nudge-off"' in box and "Nothing sent yet." in box
        code, _, out = ask(kb, "POST", "/api/nudge", {"do": "test", "lang": "en"})
        assert code == 200 and json.loads(out)["say"] == "Sent. Look at your phone."
        assert phone.got[-1]["title"] == "kb · test" and phone.got[-1]["topic"] == topic
        ask(kb, "GET", "/", host="artgate.tail1234.ts.net")          # the address a tap on a note opens
        assert kb.nudge.state()["page"] == "https://artgate.tail1234.ts.net/"
        assert kb.nudge_tick(datetime(2026, 11, 25, 9)) == ["morning:2026-11-25"]
        note = phone.got[-1]
        assert note["title"] == "kb · صباح الخير" and note["click"] == "https://artgate.tail1234.ts.net/"
        assert "ينتظرك:" in note["message"]                          # what waits on you, from the cards
        _, _, doc = ask(kb, "GET", "/")
        assert "Last sent: 2026-11-25 09:00 kb · صباح الخير" in doc
        ask(kb, "POST", "/api/nudge", {"do": "off"})
        assert kb.nudge_tick(datetime(2026, 11, 26, 9)) == []
        assert 'id="nudge-on"' in ask(kb, "GET", "/")[2]
    finally:
        srv.shutdown()
        srv.server_close()
