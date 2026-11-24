"""kb serve and kb models add: the phone page saves through the same rules as the command line, and only to its
own pages; a provider entry is written without editing JSON by hand.

The models here are stand-ins on this machine. Nothing leaves it.
"""

from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

import pytest
from standin import StandIn
from test_advise_scout import _setup, two_minds

from knowledgebreeder.cli import main
from knowledgebreeder.models import config
from knowledgebreeder.picture import lessons, serve
from knowledgebreeder.runlog import RunLog, query


# ---- kb models add -------------------------------------------------------------------------------------------
def test_a_provider_is_added_without_touching_the_others(tmp_path, capsys):
    f = tmp_path / "models.json"
    f.write_text(json.dumps({"default": "local", "models": {"local": {"url": "http://127.0.0.1:11434/v1",
                                                                      "model": "qwen"}}}), encoding="utf-8")
    assert main(["models", "--file", str(f), "add", "gemini"]) == 0
    out = capsys.readouterr().out
    book = json.loads(f.read_text(encoding="utf-8"))
    assert book["default"] == "local" and book["models"]["local"]["model"] == "qwen"   # the rest is as it was
    assert book["models"]["gemini"]["key_env"] == "GEMINI_API_KEY"
    assert not any("key" == k.lower() or "api_key" == k.lower() for k in book["models"]["gemini"])
    assert "https://aistudio.google.com/apikey" in out and "read -rs GEMINI_API_KEY && export GEMINI_API_KEY" in out
    assert "kb models check gemini --allow gemini" in out and "--models local,gemini --allow gemini" in out
    assert "(outside)" in out                                                     # it says where the data goes

    assert main(["models", "--file", str(f), "add", "gemini"]) == 2               # never written over by surprise
    assert "already has an entry called 'gemini'" in capsys.readouterr().err
    assert main(["models", "--file", str(f), "add", "claude", "--as", "sonnet", "--model", "claude-haiku-5-5"]) == 0
    capsys.readouterr()
    book = json.loads(f.read_text(encoding="utf-8"))
    assert book["models"]["sonnet"]["protocol"] == "anthropic" and book["models"]["sonnet"]["model"] == "claude-haiku-5-5"
    assert main(["models", "--file", str(f), "add", "grok"]) == 2
    assert "It knows: openai, gemini, kimi, deepseek, claude." in capsys.readouterr().err

    fresh = tmp_path / "new" / "models.json"                                      # no file yet: it becomes the default
    m, _ = config.add_preset(fresh, "deepseek")
    assert m.key_env == "DEEPSEEK_API_KEY" and json.loads(fresh.read_text())["default"] == "deepseek"
    for name, p in config.PRESETS.items():                                         # every preset is a valid entry
        config._entry(name, p["entry"], "presets")
        assert p["key_page"].startswith("https://") and p["data"]


def test_allow_takes_several_names_at_once(tmp_path, capsys):
    with StandIn(two_minds) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv)
        assert main(["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db,
                     "--models", "small,big", "--allow", "small,big", "--today", "2026-11-20"]) == 0
    assert "Recorded as run_" in capsys.readouterr().out


# ---- kb serve ------------------------------------------------------------------------------------------------
@pytest.fixture()
def served(tmp_path, capsys):
    """A run log with one run from two models, and kb serve on a free port of 127.0.0.1."""
    with StandIn(two_minds) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv)
        assert main(["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db,
                     "--today", "2026-11-20", "--models", "small,big"]) == 0
    run_id = re.search(r"Recorded as (run_\w+)", capsys.readouterr().out).group(1)
    kb = serve.Kb(db, tmp_path / "w" / "lessons.md", 0)
    srv = serve.make(kb)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield kb, run_id, db
    srv.shutdown()
    srv.server_close()


def ask(kb, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", kb.port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{kb.port}"}
    if body is not None:
        h |= {"Content-Type": "application/json", "X-KB": "1"}
    h |= headers or {}
    c.request(method, path, body=None if body is None else json.dumps(body), headers=h)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read().decode("utf-8")
    c.close()
    return out


def test_the_server_answers_only_on_this_machine_and_to_its_own_names(served):
    kb, run_id, _ = served
    code, head, doc = ask(kb, "GET", "/")
    assert code == 200 and "<h1>Your kb</h1>" in doc and run_id in doc and "small, big" in doc and "not rated yet" in doc
    assert "connect-src 'self'" in head["Content-Security-Policy"] and "frame-ancestors 'none'" in head["Content-Security-Policy"]
    assert head["X-Frame-Options"] == "DENY" and head["Cache-Control"] == "no-store" and head["Referrer-Policy"] == "no-referrer"
    assert not re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", doc)     # nothing fetched from outside
    assert ask(kb, "GET", "/", host="evil.example")[0] == 421                    # a renamed address is refused
    assert ask(kb, "GET", "/", host=f"127.0.0.1:{kb.port + 1}")[0] == 421
    assert ask(kb, "GET", "/", host="artgate.tail1234.ts.net")[0] == 200       # tailscale serve keeps the name
    _, _, doc = ask(kb, "GET", "/", headers={"Tailscale-User-Login": "someone@example.com"})
    assert "Opened as someone@example.com through your tailnet." in doc
    assert ask(kb, "GET", "/?lang=ar")[2].count('dir="rtl"') == 1
    assert ask(kb, "GET", "/run/run_nothere0000")[0] == 404 and ask(kb, "GET", "/etc/passwd")[0] == 404
    assert ask(kb, "GET", "/favicon.ico")[0] == 204

    code, _, doc = ask(kb, "GET", f"/run/{run_id}")
    assert code == 200 and '"live": true' in doc and 'class="save"' in doc and 'class="copy"' not in doc
    assert "connect-src 'self'" in doc and 'href="/?lang=en"' in doc               # the page may save, and go back
    assert "<script>alert(1)" not in doc


def test_changes_come_only_from_its_own_pages(served):
    kb, run_id, db = served
    good = {"run": run_id, "worker": "small", "pieces": [1]}
    assert ask(kb, "POST", "/api/rate", good, headers={"X-KB": "0"})[0] == 403     # a plain form from elsewhere
    assert ask(kb, "POST", "/api/rate", good, headers={"Origin": "https://evil.example"})[0] == 403
    assert ask(kb, "POST", "/api/rate", good, headers={"Content-Type": "text/plain"})[0] == 415
    assert ask(kb, "POST", "/api/rate", good, host="evil.example")[0] == 421
    assert ask(kb, "POST", "/api/lesson", {"text": "x" * (serve.MAX_BODY + 10)})[0] == 413
    assert ask(kb, "POST", "/api/nothing", {"x": 1})[0] == 404
    log = RunLog(db)
    assert not any({"would_act", "picked"} & set(s["scores"]) for s in query.show(log, run_id)["steps"])  # nothing written
    log.close()


def test_ticks_picks_and_lessons_save_from_the_phone(served):
    kb, run_id, db = served
    o = {"Origin": f"http://127.0.0.1:{kb.port}"}
    code, _, said = ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "small", "pieces": [1, 3], "why": "the class is soon"}, o)
    assert code == 200 and json.loads(said)["share"] == pytest.approx(2 / 3)
    code, _, said = ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "small", "pieces": [2]}, o)
    assert code == 400 and "already recorded for small" in json.loads(said)["error"]   # once per answer, as on the CLI
    code, _, said = ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": [9]}, o)
    assert code == 400 and "numbered 1 to 3" in json.loads(said)["error"]
    assert ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": ["1; rm"]}, o)[0] == 400
    assert ask(kb, "POST", "/api/rate", {"run": run_id, "worker": "big", "pieces": []}, o)[0] == 200   # none of them
    assert ask(kb, "POST", "/api/pick", {"run": run_id, "worker": "nobody"}, o)[0] == 400
    assert ask(kb, "POST", "/api/pick", {"run": run_id, "worker": "big"}, o)[0] == 200
    assert ask(kb, "POST", "/api/pick", {"run": run_id, "worker": "small"}, o)[0] == 400
    ts = {"Origin": "https://artgate.tail1234.ts.net"}                             # through tailscale serve,
    assert ask(kb, "POST", "/api/lesson", {"text": "Kept from the phone."}, ts)[0] == 200    # Host rewritten or not
    assert ask(kb, "POST", "/api/lesson", {"text": "Kept twice."}, ts, host="artgate.tail1234.ts.net")[0] == 200

    log = RunLog(db)
    notes = {s["worker"]: s["scores"] for s in query.show(log, run_id)["steps"]}
    log.close()
    assert notes["small"]["would_act"] == pytest.approx(2 / 3) and notes["big"]["would_act"] == 0
    assert notes["big"]["picked"] == 1 and notes["small"]["picked"] == 0
    _, _, doc = ask(kb, "GET", "/")
    assert "rated 2 of 2 · picked big" in doc
    _, _, doc = ask(kb, "GET", f"/run/{run_id}")
    assert 'name="pick"' not in doc and 'class="save"' not in doc                 # recorded, so nothing left to save

    assert ask(kb, "POST", "/api/lesson", {"text": "  Quiet is   not dead. "}, o)[0] == 200
    code, _, said = ask(kb, "POST", "/api/lesson", {"text": "quiet is not dead."}, o)
    assert code == 200 and json.loads(said)["new"] is False
    assert ask(kb, "POST", "/api/lesson", {"text": "   "}, o)[0] == 400
    assert lessons.read(kb.lessons) == ["Kept from the phone.", "Kept twice.", "Quiet is not dead."]
    assert "Quiet is not dead." in ask(kb, "GET", "/")[2]


def test_serve_without_a_run_log_says_what_to_do(tmp_path):
    kb = serve.Kb(tmp_path / "none.db", tmp_path / "lessons.md", 0)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code, _, doc = ask(kb, "GET", "/")
        assert code == 200 and "No advice run yet. Press Ask for advice." in doc and 'id="ask"' in doc
        assert ask(kb, "POST", "/api/rate", {"run": "run_x", "pieces": []})[0] == 404
        assert not Path(tmp_path / "none.db").exists()                               # looking creates nothing
    finally:
        srv.shutdown()
        srv.server_close()
    assert serve.host_ok("localhost:8765", 8765) and serve.host_ok("[::1]:8765", 8765)
    assert not serve.host_ok("localhost", 8765) and not serve.host_ok(None, 8765)
    assert not serve.host_ok("ts.net.evil.example", 8765) and not serve.host_ok("a.ts.net:8080", 8765)


def test_a_taken_port_is_named_with_the_next_one_to_try(tmp_path, capsys):
    kb = serve.Kb(tmp_path / "none.db", tmp_path / "lessons.md", 0)
    srv = serve.make(kb)
    try:
        assert main(["serve", "--port", str(kb.port), "--runlog", str(tmp_path / "none.db")]) == 2
        assert f"kb serve --port {kb.port + 1}" in capsys.readouterr().err
    finally:
        srv.server_close()
