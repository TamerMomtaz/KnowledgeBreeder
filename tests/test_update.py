"""kb keeps itself up to date: Update kb on the page, kb update, and the nightly timer. Plus the menu bar."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading

import pytest
from test_explain import _text
from test_serve import ask

from knowledgebreeder import update
from knowledgebreeder.picture import serve


def fake_git(behind=2, dirty="", branch="main", changed="knowledgebreeder/x.py", calls=None):
    """A stand-in for git and systemd: nothing runs, nothing is fetched."""
    calls = [] if calls is None else calls

    def run(cmd):
        calls.append(cmd)
        out = ""
        if cmd[0] == "git":
            a = cmd[3:]
            out = {"fetch": "", "merge": "", "status": dirty, "diff": changed,
                   "rev-list": str(behind),
                   "rev-parse": branch if "--abbrev-ref" in a else "abc123"}[a[0]]
        return subprocess.CompletedProcess(cmd, 0, out, "")
    return run


def test_update_brings_new_code_down_and_installs_only_when_packages_changed(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []
    got = update.apply(tmp_path, fake_git(calls=calls), python="/venv/python")
    assert got == {"updated": 2, "installed": False}
    assert ["git", "-C", str(tmp_path), "merge", "--ff-only", "--quiet", "origin/main"] in calls
    assert not any("pip" in c for c in calls)
    calls.clear()
    got = update.apply(tmp_path, fake_git(changed="pyproject.toml\nREADME.md", calls=calls), python="/venv/python")
    assert got["installed"] is True and ["/venv/python", "-m", "pip", "install", "--quiet", "-e", str(tmp_path)] in calls
    assert update.apply(tmp_path, fake_git(behind=0)) == {"updated": 0, "installed": False}


def test_update_leaves_your_changes_and_other_branches_alone(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []
    with pytest.raises(update.UpdateError, match="changed on this laptop"):
        update.apply(tmp_path, fake_git(dirty=" M knowledgebreeder/cli.py", calls=calls))
    with pytest.raises(update.UpdateError, match="on the branch my-work, not main"):
        update.apply(tmp_path, fake_git(branch="my-work", calls=calls))
    assert not any("merge" in c for c in calls)
    with pytest.raises(update.UpdateError, match="not a git copy"):
        update.apply(tmp_path / "elsewhere", fake_git())


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_update_on_a_real_clone(tmp_path):
    def git(*a, cwd):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd, check=True,
                       capture_output=True)
    up = tmp_path / "github"
    up.mkdir()
    git("init", "-q", "-b", "main", cwd=up)
    (up / "a.txt").write_text("one\n")
    git("add", ".", cwd=up)
    git("commit", "-qm", "one", cwd=up)
    here = tmp_path / "laptop"
    git("clone", "-q", str(up), str(here), cwd=tmp_path)
    (up / "a.txt").write_text("two\n")
    git("commit", "-qam", "two", cwd=up)
    assert update.state(here)["behind"] == 1
    assert update.apply(here) == {"updated": 1, "installed": False}
    assert (here / "a.txt").read_text() == "two\n" and update.state(here)["behind"] == 0
    (up / "a.txt").write_text("three\n")
    git("commit", "-qam", "three", cwd=up)
    (here / "a.txt").write_text("mine\n")                  # a change made on the laptop stays
    with pytest.raises(update.UpdateError, match="changed on this laptop"):
        update.apply(here)
    assert (here / "a.txt").read_text() == "mine\n"


def test_the_page_offers_update_kb_and_a_menu_bar(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(update, "root", lambda: tmp_path)
    w = tmp_path / "w"
    w.mkdir()
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0)
    calls = []
    kb.update_run = fake_git(behind=3, calls=calls)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        doc = ask(kb, "GET", "/")[2]
        assert 'id="up-go"' not in doc                       # not checked yet: nothing to press
        bar = doc.split('<nav class="boxes"', 1)[1].split("</nav>", 1)[0]
        assert 'href="#all"' in bar and 'href="#inbox"' in bar and 'href="#lessons"' in bar
        assert ">All<" in bar and "Your inbox" in _text(bar)
        assert kb.check_update()["behind"] == 3
        doc = ask(kb, "GET", "/")[2]
        assert 'id="up-go"' in doc and "3 change(s) from GitHub" in doc and "Update kb" in doc
        code, _, out = ask(kb, "POST", "/api/update", {"lang": "en"})
        got = json.loads(out)
        assert code == 200 and got["updated"] == 3 and got["restart"] is False and "Ctrl+C" in got["say"]
        assert any(c[3:5] == ["merge", "--ff-only"] for c in calls)
        assert 'id="up-go"' not in ask(kb, "GET", "/")[2]
        kb.update_run = fake_git(dirty=" M x.py")
        code, _, out = ask(kb, "POST", "/api/update", {"lang": "en"})
        assert code == 400 and "changed on this laptop" in json.loads(out)["error"]
        ar = ask(kb, "GET", "/?lang=ar")[2]
        assert "الكل" in ar.split('<nav class="boxes"', 1)[1].split("</nav>", 1)[0]
    finally:
        srv.shutdown()
        srv.server_close()


def test_update_restarts_kb_serve_through_systemd_when_it_runs_there(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "abc")
    monkeypatch.setattr(update.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []
    assert update.restart_soon(fake_git(calls=calls)) is True
    assert calls[0][:2] == ["systemd-run", "--user"] and calls[0][-3:] == ["--user", "restart", "kb-serve.service"]
    monkeypatch.delenv("INVOCATION_ID")
    assert update.restart_soon(fake_git()) is False


def test_the_page_asks_for_new_code_each_time_it_opens_at_most_once_a_minute(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(update, "root", lambda: tmp_path)
    w = tmp_path / "w"
    w.mkdir()
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0)
    calls = []
    kb.update_run = fake_git(behind=0, calls=calls)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        doc = ask(kb, "GET", "/")[2]
        assert '{check: true}' in doc                        # the page asks on opening when no button shows
        code, _, out = ask(kb, "POST", "/api/update", {"check": True})
        assert code == 200 and json.loads(out)["behind"] == 0
        fetches = sum(1 for c in calls if "fetch" in c)
        kb.update_run = fake_git(behind=2, calls=calls)
        ask(kb, "POST", "/api/update", {"check": True})      # asked again within the minute: GitHub is not asked
        assert sum(1 for c in calls if "fetch" in c) == fetches
        kb.update_checked -= 61
        code, _, out = ask(kb, "POST", "/api/update", {"check": True})
        assert json.loads(out)["behind"] == 2 and not any("merge" in c for c in calls)
        assert 'id="up-go"' in ask(kb, "GET", "/")[2]
    finally:
        srv.shutdown()
        srv.server_close()
