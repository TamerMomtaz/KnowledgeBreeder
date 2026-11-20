"""The models file, the gate that decides where a prompt may go, and the two protocols, against a stand-in server."""

from __future__ import annotations

import json

import pytest

from knowledgebreeder import models
from knowledgebreeder.cli import main
from knowledgebreeder.models import HERE, NETWORK, OUTSIDE, client, config
from knowledgebreeder.models.config import Model

from standin import StandIn


def test_only_a_loopback_address_counts_as_this_machine():
    where = lambda url: models.place(url)[1]
    for url in ("http://localhost:11434/v1", "http://127.0.0.1:8080/v1", "http://[::1]:1/v1", "http://kb.localhost/v1"):
        assert where(url) == HERE
    for url in ("http://192.168.1.20:11434/v1", "http://10.0.0.7/v1", "http://[fd00::1]/v1"):
        assert where(url) == NETWORK
    for url in ("https://api.anthropic.com", "http://tower.local:11434/v1", "http://localhost@far.example/v1",
                "http://127.0.0.1.far.example/v1", "http://2130706433/v1", "http://0.0.0.0:1/v1", "http://8.8.8.8/v1"):
        assert where(url) == OUTSIDE                        # a name kb cannot place is treated as outside
    assert models.place("http://localhost@far.example/v1")[0] == "far.example"
    with pytest.raises(models.ModelError):
        models.place("file:///etc/passwd")


def test_what_the_gate_allows():
    here = Model("local", "openai", "http://localhost:11434/v1", "m")
    tower = Model("tower", "openai", "http://192.168.1.20:11434/v1", "m")
    mine = Model("tower", "openai", "http://192.168.1.20:11434/v1", "m", lan=True)
    key = Model("key", "anthropic", config.CLAUDE_API, "m", lan=True)      # "lan" cannot open an outside address
    assert models.allowed(here) and not models.allowed(tower) and models.allowed(mine) and not models.allowed(key)
    assert models.allowed(tower, ["tower"]) and models.allowed(key, {"key"}) and not models.allowed(key, {"tower"})
    with pytest.raises(models.Refused) as e:                # refused before any connection is tried
        models.ask(key, "s", "u" * 499, sending="your cards")
    msg = str(e.value)
    assert msg.startswith("Nothing was sent.") and "api.anthropic.com" in msg and "500 characters (your cards)" in msg
    assert msg.endswith("--allow key")
    with pytest.raises(models.Refused, match='"lan": true'):
        models.ask(tower, "s", "u")
    with pytest.raises(models.Refused):
        models.offered(key)


def test_a_refused_call_sends_nothing_and_an_allowed_one_goes(monkeypatch):
    with StandIn(lambda m, s, u: "fine") as sv:
        far = Model("far", "openai", sv.url + "/v1", "small")
        real = client.place
        monkeypatch.setattr(client, "place", lambda url: ("far.example", OUTSIDE) if url.startswith(sv.url) else real(url))
        with pytest.raises(models.Refused):
            models.ask(far, "s", "u")
        with pytest.raises(models.Refused):
            models.ask(far, "s", "u", allow={"someone-else"})
        assert sv.seen == []
        a = models.ask(far, "s", "u", allow={"far"})
        assert a.text == "fine" and a.where == OUTSIDE and len(sv.posts()) == 1


def test_a_local_runtime_is_asked_and_a_wordy_answer_is_still_read(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")   # a proxy in the environment must not carry a local call away
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    say = '<think>The user wants {"not": "this"}.</think>Sure [1]! ```json\n{"ok": true, "n": [1, 2]}\n```'
    with StandIn(lambda m, s, u: say) as sv:
        m = Model("local", "openai", sv.url + "/v1", "small", price_in=1.0, price_out=2.0, extra={"temperature": 0})
        obj, a = models.ask_json(m, "sys", "user")
        assert obj == {"ok": True, "n": [1, 2]} and a.where == HERE and a.worker == "local" and a.model == "small"
        assert a.tokens_in and a.tokens_out and a.cost == round((a.tokens_in + 2 * a.tokens_out) / 1e6, 6)
        body = sv.posts()[0]["body"]
        assert body["temperature"] == 0 and body["stream"] is False and [x["role"] for x in body["messages"]] == ["system", "user"]
        assert "Authorization" not in sv.posts()[0]["headers"]
        assert models.offered(m) == ["small", "big"]
    assert models.json_from('words {"a": 1} more') == {"a": 1} and models.json_from("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        models.json_from("no json here [not, json]")


def test_one_more_try_when_the_answer_is_not_json():
    said = iter(["I think the answer is yes.", '{"ok": 1}'])
    with StandIn(lambda m, s, u: next(said)) as sv:
        obj, a = models.ask_json(Model("local", "openai", sv.url + "/v1", "small"), "s", "u")
        assert obj == {"ok": 1} and "asked once more" in a.warnings[-1] and len(sv.posts()) == 2
        assert "could not be read as JSON" in sv.posts()[1]["body"]["messages"][1]["content"]
    with StandIn(lambda m, s, u: "never json") as sv:
        with pytest.raises(models.ModelError, match="did not answer in JSON, twice"):
            models.ask_json(Model("local", "openai", sv.url + "/v1", "small"), "s", "u")


def test_what_can_go_wrong_is_said_plainly():
    with StandIn(lambda m, s, u: 500) as sv:
        with pytest.raises(models.ModelError, match="answered 500"):
            models.ask(Model("local", "openai", sv.url + "/v1", "small"), "s", "u")
        sv.redirect_to = "http://far.example/v1/chat/completions"
        with pytest.raises(models.ModelError, match="kb did not follow it"):      # a local server cannot pass it on
            models.ask(Model("hop", "openai", sv.url + "/hop/v1", "small"), "s", "u")
    with StandIn(lambda m, s, u: "   ") as sv:
        with pytest.raises(models.ModelError, match="returned no text"):
            models.ask(Model("local", "openai", sv.url + "/v1", "small"), "s", "u")
    with pytest.raises(models.ModelError, match="Is the runtime running"):
        models.ask(Model("dead", "openai", "http://127.0.0.1:9/v1", "small", timeout=3), "s", "u")


def test_a_key_comes_from_the_environment_and_goes_nowhere_else(monkeypatch):
    monkeypatch.delenv("KB_TEST_KEY", raising=False)
    with StandIn(lambda m, s, u: "ok") as sv:
        m = Model("hosted", "openai", sv.url + "/v1", "small", key_env="KB_TEST_KEY")
        with pytest.raises(models.ModelError, match="KB_TEST_KEY, which is not set"):
            models.ask(m, "s", "u")
        monkeypatch.setenv("KB_TEST_KEY", "not-a-real-key-123")
        models.ask(m, "s", "u")
        assert sv.posts()[0]["headers"]["Authorization"] == "Bearer not-a-real-key-123"
        assert "not-a-real-key-123" not in repr(m)


def test_the_claude_api_goes_through_the_official_sdk(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("KB_TEST_KEY", "not-a-real-key-123")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://far.example")       # the entry's address wins, not the environment
    said = {"text": '{"ok": true}'}
    with StandIn(lambda m, s, u: said["text"]) as sv:
        key = Model("key", "anthropic", sv.url, "claude-opus-5-5", key_env="KB_TEST_KEY", fallbacks="default",
                    price_in=4.0, price_out=20.0, effort="high")
        obj, a = models.ask_json(key, "the system", "the user")
        post = sv.posts()[0]
        head = {k.lower(): v for k, v in post["headers"].items()}
        assert obj == {"ok": True} and a.model == "claude-opus-5-5" and a.cost is not None
        assert post["path"].startswith("/v1/messages") and any("not-a-real-key-123" in v for v in head.values())
        assert "server-side-fallback-2026-07-01" in head["anthropic-beta"]
        assert post["body"]["fallbacks"] == "default" and post["body"]["output_config"] == {"effort": "high"}
        assert post["body"]["system"] == "the system" and "temperature" not in post["body"] and "thinking" not in post["body"]
        plain = Model("key", "anthropic", sv.url, "claude-opus-5-5", key_env="KB_TEST_KEY")
        models.ask(plain, "s", "u")
        assert "fallbacks" not in sv.posts()[1]["body"] and "anthropic-beta" not in {k.lower() for k in sv.posts()[1]["headers"]}
        said["text"] = "REFUSE"
        with pytest.raises(models.ModelError, match="declined"):
            models.ask(plain, "s", "u")


def test_the_models_file(tmp_path):
    path = tmp_path / "models.json"
    write = lambda d: path.write_text(json.dumps(d), encoding="utf-8")
    write({"default": "b", "models": {"a": {"model": "one"}, "b": {"protocol": "anthropic", "model": "two", "key_env": "X"}}})
    book = models.load(path)
    assert book.get().name == "b" and book.get("a").url == config.LOCAL_URL and book.get("b").url == config.CLAUDE_API
    assert book.get("a").budget == 8_000 and book.get("b").budget == 200_000
    assert [m.name for m in book.pick("a, b,a")] == ["a", "b"] and [m.name for m in book.pick(None)] == ["b"]
    with pytest.raises(KeyError, match="no model called 'c'"):
        book.get("c")
    for bad, says in (({"models": {"a": {"model": "m", "api_key": "sk-123"}}}, "A key does not go in this file"),
                      ({"models": {"a": {"model": "m", "Token": "x"}}}, "A key does not go in this file"),
                      ({"models": {"a": {"model": "m", "colour": "red"}}}, "does not know: colour"),
                      ({"models": {"a": {"model": "m", "protocol": "smoke"}}}, "protocol 'smoke'"),
                      ({"models": {"a": {"url": "http://localhost:1/v1"}}}, "names no model"),
                      ({"default": "z", "models": {"a": {"model": "m"}}}, "default 'z'"), ({"nothing": 1}, '"models"')):
        write(bad)
        with pytest.raises(KeyError, match=says):
            models.load(path)
    with pytest.raises(KeyError, match="kb models init"):
        models.load(tmp_path / "missing.json")
    ex = config.example(["x", "y"])
    assert list(ex["models"]) == ["local", "local-2", "key"] and ex["models"]["key"]["key_env"] == "ANTHROPIC_API_KEY"
    write(ex)
    assert models.load(path).get("local-2").model == "y"    # the example is a file kb itself accepts


def test_command_line(tmp_path, capsys):
    path = str(tmp_path / "w" / "models.json")
    with StandIn(lambda m, s, u: "ready") as sv:
        assert main(["models", "--file", path, "init", "--url", sv.url + "/v1"]) == 0
        assert "2 local models" in capsys.readouterr().out
        assert main(["models", "--file", path, "init"]) == 2 and "already there" in capsys.readouterr().err
        assert main(["models", "--file", path, "list"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert [(r["name"], r["where"], r["asked_freely"]) for r in rows] == [
            ("local", HERE, True), ("local-2", HERE, True), ("key", OUTSIDE, False)]
        assert main(["models", "--file", path, "check"]) == 0
        out = {r["name"]: r for r in json.loads(capsys.readouterr().out)}
        assert out["local"]["result"] == "answered" and out["local"]["said"] == "ready"
        assert out["key"]["result"].startswith("not asked") and "--allow key" in out["key"]["result"]
        assert all("messages" not in p["path"] for p in sv.posts())                # the key entry was never called


def test_a_name_without_a_tag_matches_the_runtimes_latest(tmp_path, capsys):
    path = tmp_path / "models.json"
    with StandIn(lambda m, s, u: "ready", models=("kb-qwen:latest", "qwen3.6:27b")) as sv:
        path.write_text(json.dumps({"models": {"local": {"url": sv.url + "/v1", "model": "kb-qwen"},
                                               "other": {"url": sv.url + "/v1", "model": "gone"}}}))
        assert main(["models", "--file", str(path), "check"]) == 0
        out = {r["name"]: r for r in json.loads(capsys.readouterr().out)}
    assert "note" not in out["local"] and out["local"]["result"] == "answered"
    assert out["other"]["note"] == "the runtime does not list 'gone'"
