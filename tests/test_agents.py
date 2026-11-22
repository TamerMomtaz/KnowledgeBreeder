"""The register of agents: one record each, read from a file in plain words, and what in it needs a person's look.

The agents are invented (tests/fixtures/demo_agents.md). The checks follow ARM's five layers: who answers for an
agent, who ratifies before it acts, how to stop it, what it holds, and whom it passes work to.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from knowledgebreeder import agents
from knowledgebreeder.cli import main
from knowledgebreeder.models import HERE, NETWORK, OUTSIDE
from knowledgebreeder.picture.private import Private
from knowledgebreeder.runlog import RunLog

FIX = Path(__file__).parent / "fixtures" / "demo_agents.md"
TODAY = date(2026, 11, 22)


@pytest.fixture()
def demo():
    return agents.read(FIX)


def test_the_file_is_read_in_plain_words(demo):
    assert [a.name for a in demo] == ["Order reminder", "Shop replier", "Weekly totals", "Recipe printer"]
    shop, weekly = demo[1], demo[2]
    assert shop.may == ["send", "reply"] and shop.reads == ["customer messages", "the price list"]
    assert shop.ratifies == "nobody" and not shop.ratified and shop.owner == "" and shop.passes == ["Weekly totals"]
    assert (weekly.does, weekly.sends, weekly.keys, weekly.ratifies, weekly.owner, weekly.last_run) == (     # other words
        "adds up the week's orders and posts the sheet", ["sheets.example.com"], ["SHOP_MODEL_KEY"], "Nour", "Nour",
        "2026-06-01")
    assert [a.where for a in demo] == [HERE, OUTSIDE, NETWORK, NETWORK]
    assert shop.acts == ["send", "reply"] and demo[0].acts == [] and demo[3].acts == []
    assert agents.parse(agents.TEMPLATE) == []                                    # the template is all notes


@pytest.mark.parametrize(("text", "at"), [
    ("this machine", HERE), ("my laptop", HERE), ("nowhere", HERE), ("http://127.0.0.1:11434", HERE),
    ("my network (the tower)", NETWORK), ("192.168.1.40", NETWORK), ("tailnet", NETWORK),
    ("outside (a hosting service)", OUTSIDE), ("api.example.com", OUTSIDE), ("a social network, hosted", OUTSIDE),
    ("Some Service", OUTSIDE), ("", ""),
])
def test_where_an_agent_runs_or_sends(text, at):
    assert agents.where(text) == at


@pytest.mark.parametrize(("text", "says"), [
    ("name: A\nkeys: sk-ant-abcdefghijklmnopqrstuv", "line 2 of"),
    ("name: A\nkeys: my shop key", "is not a variable name"),
    ("name: A\nname: a", "names the agent 'a' twice"),
    ("owner: Nour\nname: A", "before any 'name:'"),
    ("name:\nowner: Nour", "with no name"),
])
def test_a_file_that_holds_a_key_or_makes_no_sense_is_refused(text, says):
    with pytest.raises(KeyError) as e:
        agents.parse(text, "agents.md")
    assert says in e.value.args[0]


def test_what_needs_a_look_follows_the_five_layers(demo):
    found = agents.review(demo, TODAY, Private(["Corner kiosk"]))
    got = [(f["agent"], f["layer"]) for f in found]
    assert got == [
        ("Shop replier", "prospective review"), ("Weekly totals", "stewardship register"),
        ("Shop replier", "accountability chain"), ("Shop replier", "override protocol"),
        ("Weekly totals", "override protocol"), ("Weekly totals", "stewardship register"),
        ("Recipe printer", "inter-agent council"), ("Shop replier and Weekly totals", "stewardship register")]
    assert "may send or reply by itself and its work leaves for api.example.com" in found[0]["what"]
    assert "Corner kiosk sales, which is private" in found[1]["what"]
    assert "174 days ago, and still holds SHOP_MODEL_KEY" in found[5]["what"]
    assert all("Order reminder" not in f["agents"] for f in found)                # a sound record raises nothing
    assert agents.review(demo, TODAY)[1]["layer"] == "accountability chain"       # no private list, no such finding


def test_work_passed_on_carries_where_the_next_agent_sends_it():
    a = agents.parse("name: Drafter\nruns: this machine\nowner: Nour\nmay: draft\npasses: Mailer\n\n"
                     "name: Mailer\nruns: this machine\nsends: mail.example.com\nowner: Nour\nstop: unplug it\n")
    found = agents.review(a, TODAY)
    assert [(f["agent"], f["what"]) for f in found if f["layer"] == "prospective review"] == [
        ("Drafter", "its work leaves for mail.example.com through Mailer, and nobody ratifies first"),
        ("Mailer", "its work leaves for mail.example.com, and nobody ratifies first")]
    a[1].ratifies = "Nour"                                                        # a person's yes on the way out
    assert not [f for f in agents.review(a, TODAY) if f["layer"] == "prospective review"]


def _book(tmp_path):
    w = tmp_path / "w"
    w.mkdir(exist_ok=True)
    (w / "models.json").write_text(json.dumps({"default": "small", "models": {
        "small": {"url": "http://127.0.0.1:11434/v1", "model": "small"},
        "openai": {"url": "https://api.openai.com/v1", "model": "gpt-x", "key_env": "OPENAI_API_KEY"}}}), "utf-8")
    log = RunLog(w / "runs.db")
    run = log.start("advise", label="small,openai", subject="whole picture")
    run.record("advise", worker="small", version="small")
    run.record("advise", worker="openai", version="gpt-x")
    run.end()
    log.close()
    return str(w / "models.json"), str(w / "runs.db")


def test_kbs_own_models_are_in_the_register_and_ratified_per_run(tmp_path, capsys):
    mfile, db = _book(tmp_path)
    capsys.readouterr()
    base = ["agents", "--file", str(FIX), "--models-file", mfile, "--runlog", db, "--private", str(tmp_path / "none")]
    assert main(base + ["--json", "--today", TODAY.isoformat()]) == 0
    got = json.loads(capsys.readouterr().out)
    kb = {a["name"]: a for a in got["agents"] if a["origin"] == "kb's models file"}
    assert set(kb) == {"kb: small", "kb: openai"} and kb["kb: openai"]["where"] == OUTSIDE
    assert kb["kb: openai"]["sends"] == ["api.openai.com"] and kb["kb: openai"]["keys"] == ["OPENAI_API_KEY"]
    assert agents._date(kb["kb: small"]["last_run"]) and kb["kb: openai"]["ratified"]       # read from the run log
    assert not any(n.startswith("kb:") for f in got["needs_a_look"] for n in f["agents"])
    later = date.fromordinal(date.today().toordinal() + 120).isoformat()
    assert main(base + ["--today", later]) == 0                                    # a key kept long after the last run
    out = capsys.readouterr().out
    assert "kb: openai: it last ran on" in out and "still holds OPENAI_API_KEY" in out and "kb: small: it" not in out
    assert "### kb: openai (outside)" in out and "6 agents: 4 from" in out


def test_init_makes_the_file_and_never_overwrites_it(tmp_path, capsys):
    f = str(tmp_path / "w" / "agents.md")
    assert main(["agents", "init", "--file", f]) == 0
    assert "ready to fill in" in capsys.readouterr().out and Path(f).read_text(encoding="utf-8") == agents.TEMPLATE
    assert main(["agents", "init", "--file", f]) == 2
    assert "is there already" in capsys.readouterr().err
    Path(f).write_text(agents.TEMPLATE + "\nname: Order reminder\nruns: this machine\nowner: Nour\n", encoding="utf-8")
    assert main(["agents", "--file", f, "--models-file", str(tmp_path / "none.json"), "--today", "2026-11-22"]) == 0
    out = capsys.readouterr().out
    assert "1 agent: 1 from" in out and "None needs a look." in out and "### Order reminder (this machine)" in out
    assert main(["agents", "init", "--file", f, "--force"]) == 0
    assert main(["agents", "--file", str(tmp_path / "missing.md"), "--models-file", str(tmp_path / "none.json")]) == 0
    assert "Your own agents are not written yet" in capsys.readouterr().out
    Path(f).write_text("name: Leaky\nkeys: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n", encoding="utf-8")
    assert main(["agents", "--file", f, "--models-file", str(tmp_path / "none.json")]) == 2
    err = capsys.readouterr().err
    assert "line 2" in err and "looks like a real key" in err and "ghp_" not in err        # never echoed back
