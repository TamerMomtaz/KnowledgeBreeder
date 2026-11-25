"""Hybrid kb: your keys kept where the page can use them, and the page asking every model you like under a daily cap.

No test here reaches a real provider. A paid model is a stand-in on 127.0.0.1 made to look far away, or a job
runner that only records the command it was given.
"""

from __future__ import annotations

import json
import re
import stat
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest
from standin import StandIn
from test_advise_scout import CARDS, _setup, adviser
from test_explain import _boxes, _text
from test_serve import ask

from knowledgebreeder import keys
from knowledgebreeder.cli import main
from knowledgebreeder.models.config import PRESETS, set_cap
from knowledgebreeder.picture import Picture, actions, serve
from knowledgebreeder.runlog import RunLog

KEY = "sk-test-0123456789abcdef"
TODAY = datetime.now().astimezone().date()           # the laptop's own day, as kb counts spend


def test_a_key_is_kept_where_only_you_can_read_it(monkeypatch):
    f = keys.path()
    assert keys.load() == {} and keys.names() == [] and keys.have("OPENAI_API_KEY") == ""
    keys.put("OPENAI_API_KEY", f'  OPENAI_API_KEY="{KEY}"  ')                 # pasted with its name and quotes
    assert keys.load() == {"OPENAI_API_KEY": KEY} and keys.have("OPENAI_API_KEY") == "kept"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    with pytest.raises(KeyError):
        keys.put("OPENAI_API_KEY", "two words")
    with pytest.raises(KeyError):
        keys.put("not a name", KEY)
    assert keys.load() == {"OPENAI_API_KEY": KEY}                                # a bad paste changed nothing
    monkeypatch.setenv("OPENAI_API_KEY", "from-this-terminal")
    assert keys.env()["OPENAI_API_KEY"] == "from-this-terminal"                  # what you export here still wins
    monkeypatch.delenv("OPENAI_API_KEY")
    assert keys.env()["OPENAI_API_KEY"] == KEY
    assert keys.drop("OPENAI_API_KEY") and not keys.drop("OPENAI_API_KEY") and keys.load() == {}
    assert KEY not in f.read_text(encoding="utf-8")


def test_kb_keys_adds_a_provider_keeps_its_key_and_never_shows_it(tmp_path, monkeypatch, capsys):
    mfile, db = tmp_path / "w" / "models.json", str(tmp_path / "w" / "runs.db")
    monkeypatch.setattr("getpass.getpass", lambda prompt="": KEY)
    assert main(["keys", "add", "openai", "--models-file", str(mfile), "--runlog", db]) == 0
    out = capsys.readouterr().out
    assert KEY not in out and "Added 'openai'" in out and "https://platform.openai.com/api-keys" in out
    assert "The page now asks openai" in out and "kb models check openai --allow openai" in out
    assert keys.load() == {"OPENAI_API_KEY": KEY}
    assert main(["keys", "add", "\u2068gemini\u2069", "--models-file", str(mfile)]) == 0   # copied from the Arabic page
    assert "does not know gemini's price, so the page leaves it out" in capsys.readouterr().out
    assert main(["keys", "--models-file", str(mfile), "--runlog", db]) == 0
    out = capsys.readouterr().out
    assert KEY not in out and "- openai: Key kept as OPENAI_API_KEY. The page asks it." in out
    assert "- gemini: Key kept as GEMINI_API_KEY. kb does not know its price" in out
    assert "Spent today on paid models: $0.00 of your $1.00 a day." in out
    assert main(["keys", "cap", "2.5", "--models-file", str(mfile)]) == 0
    book = json.loads(mfile.read_text(encoding="utf-8"))
    assert book["daily_cap"] == 2.5 and set(book["models"]) == {"openai", "gemini"}
    assert main(["keys", "cap", "--models-file", str(mfile), "--runlog", db]) == 0
    assert "may spend $2.50 a day" in capsys.readouterr().out
    assert main(["keys", "cap", "lots", "--models-file", str(mfile)]) == 2
    assert main(["keys", "remove", "openai", "--models-file", str(mfile)]) == 0
    assert "Removed OPENAI_API_KEY" in capsys.readouterr().out and keys.names() == ["GEMINI_API_KEY"]
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "not a key")
    assert main(["keys", "add", "deepseek", "--models-file", str(mfile)]) == 2
    assert "DEEPSEEK_API_KEY" not in keys.names()


def _book(tmp_path, cap=None):
    mfile = tmp_path / "models.json"
    book = {"default": "big", "models": {
        "big": {"url": "http://127.0.0.1:9/v1", "model": "big"},
        "openai": dict(PRESETS["openai"]["entry"]),
        "gemini": dict(PRESETS["gemini"]["entry"]),                              # no price
        "kimi": dict(PRESETS["kimi"]["entry"], price_in=1.0, price_out=4.0),     # no key
        "deepseek": dict(PRESETS["deepseek"]["entry"])}}
    if cap is not None:
        book["daily_cap"] = cap
    mfile.write_text(json.dumps(book), encoding="utf-8")
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        keys.put(k, KEY)
    return mfile


def test_every_model_you_like_is_asked_while_today_stays_under_the_cap(tmp_path):
    mfile, db, today = _book(tmp_path, cap=0.5), tmp_path / "runs.db", TODAY
    c = actions.choose(mfile, db, today)
    # before a first run kb counts each paid model at the most it could cost: openai $0.40, deepseek about $0.05
    assert c["here"] == ["big"] and c["paid"] == ["openai", "deepseek"] and c["spent"] == 0 and c["cap"] == 0.5
    assert dict(c["out"]) == {"gemini": "no_price", "kimi": "no_key"}
    log = RunLog(str(db))
    run = log.start("advise", label="openai,deepseek", subject="whole picture")
    run.record("advise", worker="openai", version="x", cost=0.30, where="outside")
    run.record("advise", worker="big", version="x", cost=5.0, where="this machine")     # a local price is not spent
    old = run.record("advise", worker="deepseek", version="x", cost=9.0, where="outside")
    two_days = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="milliseconds")
    log.db.execute("UPDATE steps SET started = ? WHERE id = ?", (two_days, old))           # not today's money
    log.close()
    assert actions.spent(db, today) == 0.30
    assert actions.likely(actions.models.load(mfile).get("openai"), db) == 0.30          # the most it has cost
    c = actions.choose(mfile, db, today)
    assert c["paid"] == [] and dict(c["out"])["openai"] == "over_cap" and dict(c["out"])["deepseek"] == "over_cap"
    set_cap(mfile, 10)
    assert actions.choose(mfile, db, today)["paid"] == ["openai", "deepseek"]
    set_cap(mfile, 0)
    c = actions.choose(mfile, db, today)
    assert c["here"] == ["big"] and c["paid"] == [] and dict(c["out"])["openai"] == "cap_zero"


def test_the_page_allows_only_the_paid_models_it_chose(tmp_path):
    seen: list[list[str]] = []

    def runner(argv):
        seen.append(argv)
        return 0, json.dumps({"run": None, "results": []}), ""
    w = tmp_path / "w"
    w.mkdir()
    Picture.load(CARDS).save(w / "picture.json")
    _book(w)
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY, jobs=actions.Jobs(runner))
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        text = _text(_boxes(ask(kb, "GET", "/")[2])["ask"])
        assert "Models on this laptop: big." in text and "Paid models with your keys: openai, deepseek." in text
        assert "Spent today on paid models: $0.00 of your $1.00 a day." in text
        assert "Not asked now: gemini (kb does not know its price" in text
        assert "kimi (no key yet. On the laptop: kb keys add kimi)." in text
        code, _, said = ask(kb, "POST", "/api/advise", {"lang": "en"})
        assert code == 200 and json.loads(said)["say"].startswith("kb is asking big, openai, deepseek for advice.")
        kb.jobs.wait()
        argv = seen[0]
        assert argv[argv.index("--models") + 1] == "big,openai,deepseek"
        assert argv[argv.index("--allow") + 1] == "openai,deepseek" and argv.count("--allow") == 1
        ar = re.sub("[\u2068\u2069]", "", _text(_boxes(ask(kb, "GET", "/?lang=ar")[2])["ask"]))
        assert "النماذج المدفوعة بمفاتيحك: openai, deepseek." in ar and "لا مفتاح بعد. على اللابتوب: kb keys add kimi" in ar
    finally:
        srv.shutdown()
        srv.server_close()


def test_every_job_reads_the_keys_file_again():
    keys.put("KB_TEST_KEY", KEY)                       # kept after kb serve started: the next job has it
    code, out, _ = actions.run_cli([sys.executable, "-c", "import os; print(os.environ.get('KB_TEST_KEY', ''))"])
    assert code == 0 and out.strip() == KEY


def test_a_paid_model_with_nothing_it_may_see_does_not_stop_the_others(tmp_path, capsys, monkeypatch):
    with StandIn(adviser) as sv:
        pic, mfile, db, _ = _setup(tmp_path, sv, monkeypatch, far=True)
        pfile = str(tmp_path / "w" / "private.md")
        for c in Picture.load(pic).cards.values():
            assert main(["picture", "private", "--private", pfile, c["name"]]) == 0
        capsys.readouterr()
        code = main(["picture", "--file", pic, "advise", "--models-file", mfile, "--runlog", db, "--models",
                     "small,far", "--allow", "far", "--private", pfile, "--today", "2026-11-20", "--json"])
        out = json.loads(capsys.readouterr().out)
    assert code == 0 and [r["worker"] for r in out["results"]] == ["far", "small"]
    assert out["results"][0]["error"].startswith("every line kb could send far is private")
    assert out["results"][1]["advice"] and not any("/far/" in s["path"] for s in sv.seen)
