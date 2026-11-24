"""Where you were: browser history, the files the desktop says you opened, and the files you changed, read from a
made-up home folder. Nothing here reads the real home folder of whoever runs the tests."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from test_serve import ask

from knowledgebreeder import where as wh
from knowledgebreeder.cli import main
from knowledgebreeder.picture import serve

NOW = time.time()
HOUR = 3600.0


def _chrome(path: Path, rows: list[tuple[str, str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER)")
    con.execute("CREATE TABLE visits(id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
    for i, (url, title, ts) in enumerate(rows, 1):
        con.execute("INSERT INTO urls VALUES (?, ?, ?, 1, 0)", (i, url, title))
        con.execute("INSERT INTO visits(url, visit_time) VALUES (?, ?)", (i, int((ts + 11_644_473_600) * 1_000_000)))
    con.commit()
    con.close()


def _firefox(path: Path, rows: list[tuple[str, str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    con.execute("CREATE TABLE moz_historyvisits(id INTEGER PRIMARY KEY, place_id INTEGER, visit_date INTEGER)")
    for i, (url, title, ts) in enumerate(rows, 1):
        con.execute("INSERT INTO moz_places VALUES (?, ?, ?)", (i, url, title))
        con.execute("INSERT INTO moz_historyvisits(place_id, visit_date) VALUES (?, ?)", (i, int(ts * 1_000_000)))
    con.commit()
    con.close()


def _touch(path: Path, ts: float, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (ts, ts))
    return path


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    old = NOW - 40 * 24 * HOUR
    _chrome(h / ".config/google-chrome/Default/History", [
        ("https://claude.ai/chat/7f3a", "Algorithmic reverse engineering of habits - Claude", NOW - 2 * HOUR),
        ("https://claude.ai/chat/7f3a", "Algorithmic reverse engineering of habits - Claude", NOW - 3 * HOUR),
        ("https://www.google.com/search?q=algorithmic+reverse+engineering&oq=algo", "algorithmic reverse engineering - Google Search", NOW - 4 * HOUR),
        ("https://docs.google.com/document/d/abc/edit?usp=sharing&access_token=SECRET123", "Bakery plan", NOW - 5 * HOUR),
        ("https://example.com/news?utm_source=x&id=7", "A news page", NOW - 6 * HOUR),
        ("http://127.0.0.1:8765/", "Your kb", NOW - 1 * HOUR),
        ("chrome://settings/", "Settings", NOW - 1 * HOUR),
        ("https://chatgpt.com/c/old", "An old chat", old),
    ])
    _firefox(h / ".mozilla/firefox/abcd.default-release/places.sqlite", [
        ("https://arxiv.org/abs/2601.00001", "A paper on behaviour models", NOW - 7 * HOUR),
    ])
    research = _touch(h / "Documents/research/reverse-engineering-notes.md", NOW - 8 * HOUR, "my notes on the research")
    _touch(h / "Documents/research/sources.md", NOW - 9 * HOUR)
    _touch(h / "Documents/old.md", old)
    _touch(h / ".secret/hidden.md", NOW - HOUR)
    _touch(h / "code/app/node_modules/pkg/index.js", NOW - HOUR)
    _touch(h / "code/app/main.pyc", NOW - HOUR)
    xbel = h / ".local/share/recently-used.xbel"
    xbel.parent.mkdir(parents=True, exist_ok=True)
    xbel.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<xbel version="1.0" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"
      xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info">
  <bookmark href="file://{research.as_posix().replace(' ', '%20')}" added="{_iso(NOW - 30 * HOUR)}" modified="{_iso(NOW - 8 * HOUR)}" visited="{_iso(NOW - 8 * HOUR)}">
    <info><metadata owner="http://freedesktop.org"><mime:mime-type type="text/markdown"/>
      <bookmark:applications><bookmark:application name="Text Editor" exec="'gnome-text-editor %u'" modified="{_iso(NOW - 8 * HOUR)}" count="3"/></bookmark:applications>
    </metadata></info>
  </bookmark>
  <bookmark href="file:///nowhere/gone.pdf" added="{_iso(NOW - 10 * HOUR)}" modified="{_iso(NOW - 10 * HOUR)}" visited="{_iso(NOW - 10 * HOUR)}"/>
  <bookmark href="file:///nowhere/ancient.pdf" added="{_iso(old)}" modified="{_iso(old)}" visited="{_iso(old)}"/>
</xbel>''', encoding="utf-8")
    return h


def test_it_finds_the_ai_chats_searches_documents_and_files_of_the_last_days(home):
    d = wh.gather(30, home, now=NOW)
    c = wh.counts(d["items"])
    assert d["browsers"] == ["Chrome", "Firefox"] and not d["problems"] and not d["stopped"]
    assert c == {"ai": 1, "search": 1, "doc": 2, "opened": 2, "changed": 2, "web": 1}
    chat = next(x for x in d["items"] if x["kind"] == "ai")
    assert chat["title"].startswith("Algorithmic reverse engineering") and chat["count"] == 2   # one line, two visits
    assert next(x for x in d["items"] if x["kind"] == "search")["title"] == "algorithmic reverse engineering"
    whole = json.dumps(d)
    assert "SECRET123" not in whole and "utm_source" not in whole        # keys and tracking are never shown
    assert "127.0.0.1" not in whole and "chrome://" not in whole          # kb's own page and browser pages are left out
    assert "hidden.md" not in whole and "node_modules" not in whole and "main.pyc" not in whole
    assert "old.md" not in whole and "An old chat" not in whole and "ancient.pdf" not in whole   # older than 30 days
    opened = {x["title"]: x for x in d["items"] if x["kind"] == "opened"}
    assert opened["reverse-engineering-notes.md"]["via"] == "Text Editor" and opened["gone.pdf"]["gone"]
    assert [x["ts"] for x in d["items"]] == sorted((x["ts"] for x in d["items"]), reverse=True)


def test_since_yesterday_means_from_midnight_yesterday_and_a_word_finds_the_lost_research(home):
    start = wh.since(2, NOW)
    assert wh.local(start).hour == 0 and NOW - start <= 48 * HOUR
    d = wh.gather(30, home, now=NOW)
    hits = wh.find(d["items"], "Reverse ENGINEERING")
    assert {x["kind"] for x in hits} == {"ai", "search", "opened", "changed"}
    out = wh.md(d, "reverse")
    assert "## AI chats" in out and "https://claude.ai/chat/7f3a" in out and "~/Documents/research" in out
    assert "Bakery plan" not in out


def test_addresses_lose_keys_and_tracking_but_keep_what_finds_the_page():
    u = wh.clean_url("https://user:pw@docs.google.com/d/x/edit?usp=sharing&access_token=abc&X-Amz-Signature=s&q=bakery#k=1")
    assert u == "https://docs.google.com/d/x/edit?usp=sharing&q=bakery#k=1"
    assert wh.clean_url("https://app.example.com/cb#access_token=abc&state=1") == "https://app.example.com/cb"
    assert wh.kind_of("https://www.google.com.eg/search?q=%D9%81%D8%B1%D8%B5") == "search"
    assert wh.search_words("https://duckduckgo.com/?q=grant+cairo") == "grant cairo"
    assert wh.kind_of("https://kb.tail1234.ts.net/") is None and wh.kind_of("file:///etc/passwd") is None


def test_a_very_big_home_folder_is_cut_short_and_says_so(tmp_path):
    for i in range(30):
        _touch(tmp_path / f"d{i}/f.md", NOW)
    files, stopped = wh.changed([tmp_path], NOW - HOUR, max_seen=10)
    assert stopped and len(files) < 30


@pytest.fixture()
def up():
    servers = []

    def start(kb):
        srv = serve.make(kb)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return kb
    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def test_the_page_shows_nothing_until_you_turn_it_on_then_finds_and_keeps(home, tmp_path, up):
    w = tmp_path / "w"
    w.mkdir()
    kb = up(serve.Kb(w / "runs.db", w / "lessons.md", 0, today=date(2026, 11, 24), home=home))
    code, _, doc = ask(kb, "GET", "/")
    assert code == 200 and 'id="where-on"' in doc and "claude.ai" not in doc and doc.count("<script") == 2
    assert ask(kb, "GET", "/where")[0] == 303                              # off: the page sends you back
    assert ask(kb, "POST", "/api/where/keep", {"url": "https://claude.ai/chat/7f3a"})[0] == 400

    assert json.loads(ask(kb, "POST", "/api/where", {"on": True})[2])["on"] is True
    code, _, doc = ask(kb, "GET", "/")
    assert code == 200 and "Since yesterday. AI chats: 1." in doc and "https://claude.ai/chat/7f3a" in doc
    assert 'id="where-on"' not in doc and doc.count("<script") == 2
    code, head, doc = ask(kb, "GET", "/where?days=7&q=reverse")
    assert code == 200 and "default-src 'none'" in head["Content-Security-Policy"]
    assert 'aria-current="page">Last 7 days' in doc and "Bakery plan" not in doc and 'data-path="' in doc
    code, _, doc = ask(kb, "GET", "/where?lang=ar")
    assert code == 200 and doc.count('dir="rtl"') == 1 and "أين كنت" in doc and "Bakery plan" in doc

    # a page goes into the inbox as its title and address; a file as a copy; any other path is refused
    r = json.loads(ask(kb, "POST", "/api/where/keep", {"url": "https://claude.ai/chat/7f3a?token=x",
                                                        "title": "Algorithmic reverse engineering"})[2])
    assert r["say"] == "Kept in your inbox." and r["new"]
    notes = home / "Documents/research/reverse-engineering-notes.md"
    r = json.loads(ask(kb, "POST", "/api/where/keep", {"path": str(notes)})[2])
    assert r["new"]
    texts = " ".join(kb.inbox.text(x) for x in kb.inbox.items())
    assert "https://claude.ai/chat/7f3a" in texts and "token=x" not in texts and "my notes on the research" in texts
    for bad in ("/etc/passwd", str(home / ".secret/hidden.md"), str(w / "lessons.md")):
        code, _, out = ask(kb, "POST", "/api/where/keep", {"path": bad})
        assert code == 400 and "showed you" in out
    assert ask(kb, "POST", "/api/where/keep", {"url": "javascript:alert(1)"})[0] == 400

    assert json.loads(ask(kb, "POST", "/api/where", {"on": False})[2])["on"] is False
    assert 'id="where-on"' in ask(kb, "GET", "/")[2]


def test_kb_where_prints_the_same_in_the_terminal(home, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(home))
    assert main(["where", "--days", "30", "--find", "reverse"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Where you were since") and "## Searches" in out and "algorithmic reverse engineering" in out
    assert main(["where", "--days", "30", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["items"]) == 9
