"""kb keeps itself up to date, so you never type git pull.

New kb code lands on GitHub when you merge a pull request. Before this, the laptop only had it after you typed
``git pull`` and ``kb serve --install``. Now:

- the page checks GitHub every few hours and, when there is new code, shows **Update kb**. Pressing it brings the new
  code down and restarts kb; the page reloads by itself.
- ``kb serve --install`` also sets a nightly update (a systemd user timer, about 4 AM), so most days there is nothing
  to press. ``kb update`` does the same by hand.

What it never does:
- it only fast-forwards kb's own folder to GitHub's main. If you changed kb's files yourself, or the folder is on
  another branch, it stops and says so, and changes nothing.
- it touches no file of yours: cards, picture.json, work/ and keys are not part of kb's code.
- it needs no key and no sudo: kb's repository is public.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
BRANCH = "main"
SERVICE = "kb-serve.service"


class UpdateError(Exception):
    """Why kb could not update itself, as one plain sentence."""


def root() -> Path:
    """kb's own folder: the git clone this code runs from."""
    return Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)


def _git(run: Runner, where: Path, *args: str) -> str:
    r = run(["git", "-C", str(where), *args])
    if r.returncode != 0:
        said = (r.stderr or r.stdout or "").strip().splitlines()
        raise UpdateError(f"git {args[0]} did not work: {said[-1] if said else 'no reason given'}")
    return (r.stdout or "").strip()


def state(where: Path | None = None, run: Runner = _run, fetch: bool = True) -> dict:
    """How far kb's folder is behind GitHub's main. {behind, branch, dirty}. Raises UpdateError with a plain reason."""
    where = where or root()
    if not (where / ".git").exists():
        raise UpdateError(f"kb's folder {where} is not a git copy, so kb cannot update it by itself")
    if fetch:
        _git(run, where, "fetch", "--quiet", "origin", BRANCH)
    branch = _git(run, where, "rev-parse", "--abbrev-ref", "HEAD")
    behind = int(_git(run, where, "rev-list", "--count", f"HEAD..origin/{BRANCH}") or 0)
    dirty = bool(_git(run, where, "status", "--porcelain", "--untracked-files=no"))
    return {"behind": behind, "branch": branch, "dirty": dirty}


def apply(where: Path | None = None, run: Runner = _run, python: str | None = None) -> dict:
    """Bring the new code down. {updated: how many changes, installed: whether kb's packages were installed again}."""
    where = where or root()
    s = state(where, run)
    if not s["behind"]:
        return {"updated": 0, "installed": False}
    if s["branch"] != BRANCH:
        raise UpdateError(f"kb's folder is on the branch {s['branch']}, not {BRANCH}, so kb left it alone. "
                          f"Go back with: git -C {where} checkout {BRANCH}")
    if s["dirty"]:
        raise UpdateError(f"kb's own files were changed on this laptop, so kb left them alone. See what changed with: "
                          f"git -C {where} status")
    before = _git(run, where, "rev-parse", "HEAD")
    _git(run, where, "merge", "--ff-only", "--quiet", f"origin/{BRANCH}")
    changed = _git(run, where, "diff", "--name-only", before, "HEAD").splitlines()
    installed = False
    if "pyproject.toml" in changed:                       # new packages or commands: install kb again, quietly
        r = run([python or sys.executable, "-m", "pip", "install", "--quiet", "-e", str(where)])
        if r.returncode != 0:
            raise UpdateError("the new code is here, but installing its packages did not work. In a terminal type: "
                              f"pip install -e {where}")
        installed = True
    return {"updated": s["behind"], "installed": installed}


def under_service() -> bool:
    """Whether this kb serve is the one systemd started (kb serve --install)."""
    return bool(os.environ.get("INVOCATION_ID")) and shutil.which("systemd-run") is not None


def restart_soon(run: Runner = _run, seconds: int = 2) -> bool:
    """Ask systemd to restart kb serve in a moment, from outside it, so this answer reaches the page first."""
    if not under_service():
        return False
    r = run(["systemd-run", "--user", "--quiet", f"--on-active={seconds}", "--timer-property=AccuracySec=100ms",
             "systemctl", "--user", "restart", SERVICE])
    return r.returncode == 0


def service_active(run: Runner = _run) -> bool:
    if not shutil.which("systemctl"):
        return False
    r = run(["systemctl", "--user", "is-active", SERVICE])
    return (r.stdout or "").strip() == "active"


def by_hand(where: Path | None = None, run: Runner = _run) -> list[str]:
    """kb update: what the nightly timer runs, and what you can type. Plain lines to print."""
    got = apply(where, run)
    if not got["updated"]:
        return ["kb is up to date. Nothing to do."]
    said = [f"kb took {got['updated']} new change(s) from GitHub."]
    if got["installed"]:
        said.append("Its packages were installed again.")
    if service_active(run):
        run(["systemctl", "--user", "restart", SERVICE])
        said.append("kb serve restarted on the new code. Reload the page.")
    else:
        said.append("If kb serve is running in a terminal, stop it with Ctrl+C and start it again.")
    return said
