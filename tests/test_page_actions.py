"""The page's buttons: advice, the scout and new cards without a terminal, and kb serve starting by itself.

Advice and the scout run the real command in a separate process against a stand-in model on 127.0.0.1, so these
prove the plumbing and the plain sentences, not the quality of any advice.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
import time
from datetime import date

import pytest
from standin import StandIn
from test_advise_scout import CARDS, adviser, reader
from test_serve import ask

from knowledgebreeder import autostart
from knowledgebreeder.cli import main
from knowledgebreeder.picture import Picture, actions, serve
from knowledgebreeder.picture import inbox as inb

DAY = date(2026, 11, 20)


def _kb(tmp_path, url=None, jobs=None):
    w = tmp_path / "w"
    w.mkdir(exist_ok=True)
    if url:
        book = {"default": "big", "models": {"small": {"url": url + "/v1", "model": "small"},
                                             "big": {"url": url + "/v1", "model": "big"},
                                             "away": {"url": "https://api.example.com/v1", "model": "x", "key_env": "X"}}}
        (w / "models.json").write_text(json.dumps(book), encoding="utf-8")
    return serve.Kb(w / "runs.db", w / "lessons.md", 0, today=DAY, jobs=jobs)


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


def _job(kb, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = json.loads(ask(kb, "GET", "/api/job")[2])
        if j["status"] != "running":
            return j
        time.sleep(0.2)
    raise AssertionError("the job did not finish")


def test_cards_are_added_from_the_page_and_nothing_is_overwritten(tmp_path, up):
    kb = up(_kb(tmp_path))
    code, _, doc = ask(kb, "GET", "/")
    assert code == 200 and 'id="ask"' in doc and "No cards yet. Add a cards file here." in doc
    assert 'id="advise" data-job="advise" data-off disabled' in doc and doc.count("<script") == 2
    side = doc.index('<div class="side">')
    assert side < doc.index('id="ask"') < doc.index('id="lesson"')        # the buttons come first in the narrow column
    text = CARDS.read_text(encoding="utf-8")
    code, _, said = ask(kb, "POST", "/api/cards", {"name": "../../my cards.md", "text": "﻿" + text})
    r = json.loads(said)
    assert code == 200 and r["found"] == r["cards"] == 5 and len(r["added"]) == 5
    assert r["say"] == "New cards: 5. Updated: 0. Unchanged: 0. Cards in your picture now: 5."
    assert r["reload"] is True and r["link"] == "#waits" and r["link_text"] == "See where your work waits"
    _, _, doc = ask(kb, "GET", "/")                    # the page loads again: the sentence stays, the box counts the cards
    job = doc.split('id="job"')[1].split("</p>")[0]
    assert "New cards: 5." in job and 'href="#waits"' in job and 'id="waits"' in doc
    kept = list((tmp_path / "w" / "cards").iterdir())
    assert [k.name for k in kept] == ["2026-11-20-my-cards.md"] and kept[0].read_text(encoding="utf-8") == text
    assert len(Picture.load(kb.picture).cards) == 5

    again = json.loads(ask(kb, "POST", "/api/cards", {"name": "my cards.md", "text": text})[2])
    assert again["say"].startswith("New cards: 0. Updated: 0. Unchanged: 5.") and len(list(kb.cards.iterdir())) == 1
    edited = text.replace("a list of past customers", "a list of past customers and their phones", 1)
    third = json.loads(ask(kb, "POST", "/api/cards", {"name": "my cards.md", "text": edited, "lang": "ar"})[2])
    assert third["updated"] == ["Saturday baking class"] and third["changed"][0] == "ما الذي تغيّر:"
    assert third["reload"] is True and again["reload"] is False
    _, _, doc = ask(kb, "GET", "/?lang=ar")
    job = doc.split('id="job"')[1].split("</p>")[0]
    assert 'class="changed"' in job and "Saturday baking class" in job and "انظر أين ينتظر عملك" in job
    assert sorted(k.name for k in kb.cards.iterdir()) == ["2026-11-20-my-cards.md", "2026-11-20-my-cards~2.md"]
    none = json.loads(ask(kb, "POST", "/api/cards", {"name": "notes.txt", "text": "just notes"})[2])
    assert none["found"] == 0 and none["say"] == "No PROJECT CARD in notes.txt, so nothing was added."
    assert ask(kb, "POST", "/api/cards", {"name": "x.md", "text": "  "})[0] == 400
    assert ask(kb, "POST", "/api/cards", {"text": text}, {"X-KB": "0"})[0] == 403

    code, _, doc = ask(kb, "GET", "/check")
    assert code == 200 and "Is your picture ready?" in doc and "Five questions asked of your 5 cards" in doc
    assert "<script" not in doc and '<ol class="md">' in doc and 'href="/?lang=en"' in doc
    _, _, ar = ask(kb, "GET", "/check?lang=ar")
    assert ar.count('dir="rtl"') == 1 and "هذه الصفحة بالإنجليزية حاليًا." in ar
    _, _, doc = ask(kb, "GET", "/chances")
    assert "kb has not read your inbox yet." in doc
    _, _, doc = ask(kb, "GET", "/")
    assert "Your picture: 5 cards." in doc and "No model on this laptop yet" in doc and "See chances (0 open)" in doc


def test_advice_from_the_page_asks_only_this_laptops_models(tmp_path, up):
    with StandIn(adviser) as sv:
        kb = up(_kb(tmp_path, sv.url))
        assert ask(kb, "POST", "/api/cards", {"name": "cards.md", "text": CARDS.read_text(encoding="utf-8")})[0] == 200
        _, _, doc = ask(kb, "GET", "/")
        assert "Models on this laptop: big, small." in doc and 'data-off' not in doc.split('id="cards"')[0]
        code, _, said = ask(kb, "POST", "/api/advise", {"lang": "en"})
        assert code == 200 and json.loads(said)["say"] == "kb is asking big, small for advice. It can take a few minutes."
        j = _job(kb)
    assert j["status"] == "done" and j["say"] == "Advice is ready from big, small." and j["link_text"] == "Open the advice"
    run = re.fullmatch(r"/run/(run_\w+)\?lang=en", j["link"]).group(1)
    assert {s["body"]["model"] for s in sv.seen if s["body"]} == {"big", "small"}            # never the one away
    _, _, doc = ask(kb, "GET", "/")
    assert f"/run/{run}" in doc and "big, small" in doc and "Advice is ready from big, small." in doc
    assert ask(kb, "GET", f"/run/{run}")[0] == 200
    _, _, ar = ask(kb, "GET", "/api/job?lang=ar")
    assert json.loads(ar)["say"] == "النصيحة جاهزة من \u2068big, small\u2069."


def test_the_scout_reads_the_inbox_from_the_page(tmp_path, up):
    with StandIn(reader) as sv:
        kb = up(_kb(tmp_path, sv.url))
        ask(kb, "POST", "/api/cards", {"name": "cards.md", "text": CARDS.read_text(encoding="utf-8")})
        code, _, said = ask(kb, "POST", "/api/scout", {})
        assert code == 400 and json.loads(said)["say"].startswith("Your inbox has nothing kb can read yet.")
        box = inb.Inbox(kb.inbox.root)
        box.add_text("Cairo Food Makers Fund: up to 40,000 EGP toward one piece of equipment  or one delivery "
                     "vehicle. Applications close on 15 December 2026.", None, DAY, via="phone")
        code, _, said = ask(kb, "POST", "/api/scout", {"lang": "en"})
        assert code == 200 and json.loads(said)["say"] == "kb is reading your inbox with big."
        j = _job(kb)
        assert j["status"] == "done" and j["say"] == "kb read your inbox. New: 1. Chances: 1. Not confirmed: 0."
        assert j["link"] == "/chances?lang=en"
        _, _, doc = ask(kb, "GET", "/chances")
        assert "A fund that pays toward a delivery vehicle." in doc and "<h2>Chances</h2>" in doc
        assert '<span class="more"><bdi>For: Dar Bakery order book</bdi></span>' in doc
        ask(kb, "POST", "/api/scout", {})
        j = _job(kb)
        assert j["say"] == "Nothing new in your inbox to read. Read before: 1."
        _, _, doc = ask(kb, "GET", "/")
        assert "See chances (1 open)" in doc


def test_one_job_at_a_time_and_a_failure_says_why(tmp_path, up):
    gate = threading.Event()

    def slow(argv):
        gate.wait(10)
        return 2, "", "error: the picture holds no cards yet. Add some with: kb picture add CARDS.md\n"
    jobs = actions.Jobs(slow)
    with StandIn(adviser) as sv:
        kb = up(_kb(tmp_path, sv.url, jobs=jobs))
        ask(kb, "POST", "/api/cards", {"name": "cards.md", "text": CARDS.read_text(encoding="utf-8")})
        assert ask(kb, "POST", "/api/advise", {})[0] == 200
        _, _, doc = ask(kb, "GET", "/")
        assert 'data-running="1"' in doc and "kb is asking big, small for advice." in doc
        code, _, said = ask(kb, "POST", "/api/scout", {"lang": "ar"})
        assert code == 409 and json.loads(said)["say"].startswith("kb مشغول بمهمة أخرى")
        gate.set()
        j = _job(kb)
    assert j["status"] == "failed" and j["cls"] == "err"
    assert j["say"] == "It did not work: the picture holds no cards yet. Add some with: kb picture add CARDS.md"
    assert actions.why("", 3).startswith("a model off this laptop")


def test_the_page_runs_the_same_command_as_the_terminal(tmp_path):
    kb = _kb(tmp_path)
    argv = actions.advise_argv(kb, ["big", "small"], "ar")
    assert argv[1:4] == ["-m", "knowledgebreeder.cli", "picture"] and "--allow" not in argv
    assert argv[argv.index("--models") + 1] == "big,small" and argv[argv.index("--file") + 1] == str(kb.picture)
    assert argv[-2:] == ["--today", "2026-11-20"] and "--json" in argv and argv[argv.index("--lang") + 1] == "ar"
    argv = actions.scout_argv(kb, "big")
    assert argv[argv.index("read") + 1] == str(kb.inbox.root / "text") and "--allow" not in argv
    assert all(str(tmp_path) in str(a) for a in (kb.picture, kb.models, kb.private, kb.ledger, kb.cards, kb.inbox.root))


def test_kb_serve_starts_by_itself(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    calls = []

    def systemctl(cmd):
        calls.append(cmd[2:])
        return subprocess.CompletedProcess(cmd, 0, "active\n" if "is-active" in cmd else "", "")
    lines = autostart.install(["--port", "8765"], 8765, workdir=tmp_path / "my kb", run=systemctl,
                              python="/home/tee/KnowledgeBreeder/.venv/bin/python", check_port=False)
    unit = (tmp_path / "cfg" / "systemd" / "user" / "kb-serve.service").read_text(encoding="utf-8")
    assert f'WorkingDirectory="{tmp_path / "my kb"}"' in unit and "WantedBy=default.target" in unit
    assert "ExecStart=/home/tee/KnowledgeBreeder/.venv/bin/python -m knowledgebreeder.cli serve --port 8765" in unit
    assert calls[:3] == [["daemon-reload"], ["enable", "kb-serve.service"], ["restart", "kb-serve.service"]]
    assert lines[0].startswith("kb now starts by itself") and "kb serve --uninstall" in lines[-1]
    with pytest.raises(KeyError, match="without quotes"):
        autostart.unit_text(tmp_path, ["/a\"b/python"])
    assert autostart.uninstall(systemctl)[0].startswith("kb serve no longer starts by itself")
    assert not (tmp_path / "cfg" / "systemd" / "user" / "kb-serve.service").exists()
    assert "nothing to undo" in autostart.uninstall(systemctl)[0]

    def down(cmd):
        return subprocess.CompletedProcess(cmd, 0, "failed\n" if "is-active" in cmd else "", "")
    monkeypatch.setattr(autostart.time, "sleep", lambda s: None)
    with pytest.raises(KeyError, match="journalctl --user -u kb-serve.service"):
        autostart.install([], 8765, workdir=tmp_path, run=down, check_port=False)

    seen = {}
    monkeypatch.setattr(autostart, "install", lambda args, port, **k: seen.update(args=args, port=port) or ["done"])
    monkeypatch.chdir(tmp_path)
    assert main(["serve", "--install", "--port", "8800"]) == 0
    a = seen["args"]
    assert seen["port"] == 8800 and a[:4] == ["--port", "8800", "--lang", "en"]
    assert a[a.index("--file") + 1] == str(tmp_path / "work" / "picture.json") and capsys.readouterr().out == "done\n"


def test_install_stops_a_kb_serve_left_in_a_window_you_cannot_find(tmp_path, monkeypatch):
    proc = tmp_path / "proc"

    def p(pid, *args):
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")
    p(101, "/home/tee/KnowledgeBreeder/.venv/bin/python3", "/home/tee/KnowledgeBreeder/.venv/bin/kb", "serve", "--open")
    p(102, "/usr/bin/python3", "-m", "knowledgebreeder.cli", "serve")
    p(103, "/usr/bin/python3", "-m", "http.server", "8765")                  # not kb: left alone
    p(104, "/home/tee/KnowledgeBreeder/.venv/bin/kb", "serve", "--install")  # this very command
    p(105, "bash")
    (proc / "self").mkdir()
    assert autostart.old_serves(proc) == [101, 102]

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    killed = []

    def kill(pid, sig):
        killed.append(pid)
        sock.close()                                       # the old kb serve lets go of the port
    assert autostart.stop_old(port, proc, kill=kill) == [101, 102] and killed == [101, 102]
    assert autostart.port_free(port)

    asked = []

    def systemctl(cmd):                                    # not running before the install, running after it
        if "is-active" in cmd:
            asked.append(1)
        state = "active\n" if ok and len(asked) > 1 else "inactive\n"
        return subprocess.CompletedProcess(cmd, 0, state if "is-active" in cmd else "", "")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    port = busy.getsockname()[1]
    ok = False
    with pytest.raises(KeyError, match=f"fuser -k {port}/tcp"):           # nothing of kb's holds it: say how to free it
        autostart.install([], port, workdir=tmp_path, run=systemctl, stop=lambda port: [])

    def stop(port):
        busy.close()
        return [101]
    ok = True
    asked.clear()
    lines = autostart.install([], port, workdir=tmp_path, run=systemctl, stop=stop)
    assert lines[0] == "Stopped the kb serve that was still running in another window."
    assert lines[1].startswith("kb now starts by itself")
