"""kb serve starts by itself: a systemd user service, so the page is there whenever you are logged in.

``kb serve --install`` writes one small file, ``~/.config/systemd/user/kb-serve.service``, and asks systemd to start
it now and at every login. It runs the same ``kb serve`` you would type, with every path written out in full, so it
does not depend on the folder or the terminal it was started from. ``kb serve --uninstall`` takes it away again.

It needs no sudo. The service runs as you, sees only what you see, and still listens on 127.0.0.1 only. Keys you
export in a terminal are not in its environment; the keys you keep with ``kb keys add`` are, because each job reads
~/.config/kb/keys.env again.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

NAME = "kb-serve.service"
UPDATE = "kb-update.service"
UPDATE_TIMER = "kb-update.timer"
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "systemd" / "user"


def _quote(x: str) -> str:
    """One word on a systemd ExecStart line. Paths with spaces are quoted; a quote or a backslash is refused."""
    if any(c in x for c in '"\\\n%$'):
        raise KeyError(f"kb cannot write this path into the service file: {x}. Move it to a path without "
                       f"quotes, backslashes, % or $ signs.")
    return f'"{x}"' if any(c.isspace() for c in x) else x


def command(args: list[str], python: str | None = None) -> list[str]:
    """What the service runs: this Python, kb's own module, and the serve arguments."""
    return [python or sys.executable, "-m", "knowledgebreeder.cli", "serve", *args]


def unit_text(workdir: str | Path, cmd: list[str]) -> str:
    return "\n".join([
        "[Unit]",
        "Description=kb serve: your KnowledgeBreeder pages on this laptop",
        "After=network-online.target",
        "",
        "[Service]",
        f"WorkingDirectory={_quote(str(workdir))}",
        "ExecStart=" + " ".join(_quote(c) for c in cmd),
        "Restart=on-failure",
        "RestartSec=5",
        "Environment=PYTHONUNBUFFERED=1",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])


def update_units(workdir: str | Path, python: str | None = None) -> dict[str, str]:
    """The nightly update: a timer at about 4 AM runs kb update, which brings new kb code down from GitHub and
    restarts kb serve on it. Persistent: a night the laptop slept is caught up at the next start."""
    py = _quote(python or sys.executable)
    return {
        UPDATE: "\n".join([
            "[Unit]",
            "Description=kb update: bring new kb code down from GitHub and restart kb serve",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={_quote(str(workdir))}",
            f"ExecStart={py} -m knowledgebreeder.cli update",
            "",
        ]),
        UPDATE_TIMER: "\n".join([
            "[Unit]",
            "Description=kb update, every night",
            "",
            "[Timer]",
            "OnCalendar=*-*-* 04:00",
            "RandomizedDelaySec=30min",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
    }


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def old_serves(proc: str | Path = "/proc") -> list[int]:
    """kb serve processes of yours that are not this one: one left running in a terminal you can no longer find."""
    found = []
    me = {os.getpid(), os.getppid()}
    for d in Path(proc).iterdir():
        if not d.name.isdigit() or int(d.name) in me:
            continue
        try:
            if d.stat().st_uid != os.getuid():
                continue
            args = [a for a in (d / "cmdline").read_bytes().decode("utf-8", "replace").split("\0") if a]
        except OSError:
            continue
        kb = any(a == "kb" or a.endswith("/kb") or a == "knowledgebreeder.cli" for a in args)
        if kb and "serve" in args and not {"--install", "--uninstall"} & set(args):
            found.append(int(d.name))
    return sorted(found)


def stop_old(port: int, proc: str | Path = "/proc", kill=os.kill, wait: float = 5.0) -> list[int]:
    """Stop a kb serve left running elsewhere, so the service can take its port. Returns the processes stopped."""
    pids = old_serves(proc)
    for pid in pids:
        try:
            kill(pid, signal.SIGTERM)
        except OSError:
            pass
    end = time.monotonic() + wait
    while pids and not port_free(port) and time.monotonic() < end:
        time.sleep(0.2)
    return pids


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)


def _need_systemctl(run: Runner | None) -> Runner:
    if run is None:
        if not shutil.which("systemctl"):
            raise KeyError("this laptop has no systemctl, so kb cannot start by itself here. Keep a terminal open "
                           "with: kb serve")
        run = _run
    return run


def _ok(run: Runner, cmd: list[str], what: str) -> str:
    r = run(cmd)
    if r.returncode != 0:
        said = (r.stderr or r.stdout or "").strip().splitlines()
        raise KeyError(f"{what} did not work: {said[-1] if said else 'no reason given'}")
    return (r.stdout or "").strip()


def install(args: list[str], port: int, workdir: str | Path | None = None, run: Runner | None = None,
            python: str | None = None, check_port: bool = True, stop=stop_old) -> list[str]:
    """Write the service file, start it now and at every login. Returns plain lines to print."""
    run = _need_systemctl(run)
    said = []
    if check_port and not port_free(port):
        state = run(["systemctl", "--user", "is-active", NAME])
        if (state.stdout or "").strip() != "active":
            stopped = stop(port)                          # the kb serve in a window you can no longer find
            if stopped:
                said.append("Stopped the kb serve that was still running in another window.")
            if not port_free(port):
                raise KeyError(f"something else is using port {port}. Stop it with: fuser -k {port}/tcp "
                               f"Then run this again.")
    workdir = Path(workdir or os.getcwd()).resolve()
    path = unit_dir() / NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    text = unit_text(workdir, command(args, python))
    for where, words in ((path, text), *((path.parent / n, t) for n, t in update_units(workdir, python).items())):
        tmp = where.with_suffix(".part")
        tmp.write_text(words, encoding="utf-8")
        os.replace(tmp, where)
    _ok(run, ["systemctl", "--user", "daemon-reload"], "Reloading systemd")
    _ok(run, ["systemctl", "--user", "enable", NAME], "Turning on the start at login")
    _ok(run, ["systemctl", "--user", "enable", "--now", UPDATE_TIMER], "Turning on the nightly update")
    _ok(run, ["systemctl", "--user", "restart", NAME], "Starting kb serve")
    state = "?"
    for _ in range(10):
        state = (run(["systemctl", "--user", "is-active", NAME]).stdout or "").strip()
        if state == "active":
            break
        time.sleep(0.3)
    if state != "active":
        raise KeyError(f"kb serve did not start (systemd says {state or 'nothing'}). See why with: "
                       f"journalctl --user -u {NAME} -n 30")
    return [*said, "kb now starts by itself every time you log in to this laptop. It is running now.",
            f"Open it here: http://127.0.0.1:{port}/ (and on the phone, the same .ts.net address as before).",
            "You no longer need a terminal for kb serve.",
            "kb also updates itself every night at about 4 AM, so you no longer need git pull. "
            "The page shows Update kb when new code is ready sooner.",
            f"Its settings file: {path}",
            f"If the page ever does not open, see why with: journalctl --user -u {NAME} -n 30",
            "To stop it starting by itself: kb serve --uninstall"]


def uninstall(run: Runner | None = None) -> list[str]:
    run = _need_systemctl(run)
    path = unit_dir() / NAME
    if not path.exists():
        return ["kb serve was not set to start by itself, so there was nothing to undo."]
    run(["systemctl", "--user", "disable", "--now", NAME])
    run(["systemctl", "--user", "disable", "--now", UPDATE_TIMER])
    path.unlink()
    for n in (UPDATE, UPDATE_TIMER):
        (path.parent / n).unlink(missing_ok=True)
    _ok(run, ["systemctl", "--user", "daemon-reload"], "Reloading systemd")
    return ["kb serve no longer starts by itself, and it has stopped. Start it by hand with: kb serve"]
