"""Your keys for paid models, kept in one file where kb's page can use them.

A key you export in a terminal lasts until that terminal closes, and kb's page (a service that starts at login)
never sees it. So kb keeps your keys in one file on this laptop, ~/.config/kb/keys.env (KB_KEYS names another), that
only you can read (mode 600, in a folder only you can open). It is never in the repo folder, the models file, the run
log or a page, and kb never prints a key back: ``kb keys list`` shows names only.

Every kb command reads the file when it starts and fills in each key that is not set already, so a key you export in
a terminal still wins there. The page reads the file again for every job, so a key you add works on the next press,
with nothing to restart. Having a key does not send anything by itself: a model off this laptop is still asked only
when a run allows it, as the gate has always said.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path

PATH = "~/.config/kb/keys.env"
_NAME = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
_VALUE = re.compile(r"[\x21-\x7e]{8,1024}")          # printable, no spaces: every provider's keys look like this
HEAD = ("# kb keys: one NAME=key a line. Only you can read this file. Never copy it into a repo, a chat or a "
        "screenshot.\n# Change it with: kb keys add, kb keys remove. See the names with: kb keys list\n")


def path(p: str | Path | None = None) -> Path:
    return Path(p or os.environ.get("KB_KEYS") or PATH).expanduser()


def load(p: str | Path | None = None) -> dict[str, str]:
    """NAME -> key, from the file. An unreadable or missing file is no keys."""
    try:
        text = path(p).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        name, eq, value = line.strip().partition("=")
        if eq and _NAME.fullmatch(name.strip()) and value.strip():
            out[name.strip()] = value.strip()
    return out


def names(p: str | Path | None = None) -> list[str]:
    return sorted(load(p))


def clean(value: str, name: str = "") -> str:
    """The key as pasted, without a NAME= or quotes around it. Raises KeyError when it cannot be a key."""
    v = (value or "").strip()
    if name and v.startswith(name + "="):
        v = v[len(name) + 1:].strip()
    if len(v) > 1 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].strip()
    if not _VALUE.fullmatch(v):
        raise KeyError("that does not look like a key: a key is one word of letters, digits and signs, with no "
                       "spaces. Nothing was saved.")
    return v


def _write(keys: Mapping[str, str], p: str | Path | None) -> Path:
    f = path(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(f.parent, 0o700)
    except OSError:
        pass
    tmp = f.with_name(f.name + ".part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(HEAD + "".join(f"{k}={v}\n" for k, v in sorted(keys.items())))
    os.chmod(tmp, 0o600)
    os.replace(tmp, f)
    return f


def put(name: str, value: str, p: str | Path | None = None) -> Path:
    """Keep one key under its variable's name, replacing the one kept before."""
    if not _NAME.fullmatch(name or ""):
        raise KeyError(f"'{name}' cannot be a variable's name: use capital letters, digits and _.")
    keys = load(p)
    keys[name] = clean(value, name)
    return _write(keys, p)


def drop(name: str, p: str | Path | None = None) -> bool:
    keys = load(p)
    if name not in keys:
        return False
    del keys[name]
    _write(keys, p)
    return True


def env(base: Mapping[str, str] | None = None, p: str | Path | None = None) -> dict[str, str]:
    """A copy of the environment with every kept key that it does not set already."""
    out = dict(os.environ if base is None else base)
    for k, v in load(p).items():
        if not out.get(k):
            out[k] = v
    return out


def fill(target: MutableMapping[str, str] | None = None, p: str | Path | None = None) -> list[str]:
    """Put the kept keys into this process's environment, where it does not set them. Returns their names."""
    target = os.environ if target is None else target
    done = []
    for k, v in load(p).items():
        if not target.get(k):
            target[k] = v
            done.append(k)
    return done


def have(name: str | None, p: str | Path | None = None) -> str:
    """Where a key is: 'kept' (in the file, so the page can use it), 'terminal' (exported here only) or ''."""
    if not name:
        return ""
    if name in load(p):
        return "kept"
    return "terminal" if os.environ.get(name) else ""
