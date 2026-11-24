"""Where you were: the pages you visited and the files you opened or changed on this laptop, newest first, so you can
find yesterday's work again and kb can see what you have been working on.

kb reads what is already on the laptop, fresh each time, and keeps none of it:
- browser history. Chrome, Chromium, Brave, Edge, Vivaldi, Opera and Firefox each keep it in a small database in
  your home folder. The browser keeps it locked, so kb copies it to a temporary folder, reads the pages and times,
  and deletes the copy.
- the files you opened. The desktop keeps a list: ~/.local/share/recently-used.xbel (GNOME and most apps) and
  ~/.local/share/RecentDocuments (KDE).
- the files you changed. kb looks through your home folder for files changed in those days. It skips hidden
  folders, caches, code environments and kb's own work folder, and stops after a few seconds on a very big home
  folder, and says so.

Nothing here is sent anywhere or shown to a model. Addresses lose the parts that look like keys (token=, code=,
key= and the like) before kb shows them.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

# Where each browser keeps its history, under your home folder (Linux first, then macOS and Windows).
CHROMES = {
    "Chrome": [".config/google-chrome", ".config/google-chrome-beta", ".var/app/com.google.Chrome/config/google-chrome",
               "Library/Application Support/Google/Chrome", "AppData/Local/Google/Chrome/User Data"],
    "Chromium": [".config/chromium", "snap/chromium/common/chromium", ".var/app/org.chromium.Chromium/config/chromium",
                 "Library/Application Support/Chromium"],
    "Brave": [".config/BraveSoftware/Brave-Browser", ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser",
              "Library/Application Support/BraveSoftware/Brave-Browser",
              "AppData/Local/BraveSoftware/Brave-Browser/User Data"],
    "Edge": [".config/microsoft-edge", ".var/app/com.microsoft.Edge/config/microsoft-edge",
             "Library/Application Support/Microsoft Edge", "AppData/Local/Microsoft/Edge/User Data"],
    "Vivaldi": [".config/vivaldi", "Library/Application Support/Vivaldi"],
    "Opera": [".config/opera", "Library/Application Support/com.operasoftware.Opera"],
}
FIREFOXES = [".mozilla/firefox", "snap/firefox/common/.mozilla/firefox", ".var/app/org.mozilla.firefox/.mozilla/firefox",
             "Library/Application Support/Firefox/Profiles", "AppData/Roaming/Mozilla/Firefox/Profiles"]

AI = ("claude.ai", "chatgpt.com", "chat.openai.com", "gemini.google.com", "aistudio.google.com", "notebooklm.google.com",
      "perplexity.ai", "chat.deepseek.com", "kimi.com", "kimi.moonshot.cn", "grok.com", "copilot.microsoft.com",
      "chat.qwen.ai", "chat.mistral.ai", "poe.com", "manus.im", "chat.z.ai")
DOCS = ("docs.google.com", "drive.google.com", "notion.so", "notion.site", "onedrive.live.com", "sharepoint.com",
        "office.com", "dropbox.com", "github.com", "gitlab.com", "arxiv.org", "scholar.google.com", "semanticscholar.org",
        "researchgate.net", "sciencedirect.com", "springer.com", "ieeexplore.ieee.org", "dl.acm.org", "ssrn.com",
        "academia.edu", "jstor.org", "overleaf.com", "miro.com", "figma.com", "canva.com", "medium.com", "substack.com",
        "huggingface.co", "paperswithcode.com", "openreview.net", "zotero.org", "slideshare.net", "scribd.com")
SEARCH = {"google": ("/search",), "bing.com": ("/search",), "duckduckgo.com": ("/", ""), "search.brave.com": ("/search",),
          "yandex.com": ("/search", "/search/"), "search.yahoo.com": ("/search",), "ecosia.org": ("/search",)}
SKIP_HOSTS = ("localhost", "127.0.0.1", "[::1]", "accounts.google.com", "login.microsoftonline.com")

SKIP_DIRS = {"node_modules", "__pycache__", "venv", "site-packages", "snap", "target", "dist", "build", "Library",
             "AppData", "miniconda3", "anaconda3", "Trash", "go", "cache", "Cache"}
NOISE = (".pyc", ".pyo", ".o", ".so", ".tmp", ".part", ".crdownload", ".swp", ".lock", ".log", "-journal", "-wal",
         "-shm", ".lnk")
MAX_DB = 1024 * 1024 * 1024           # a history database bigger than this is not read
MAX_XBEL = 20 * 1024 * 1024
KINDS = ("ai", "search", "doc", "opened", "changed", "web")

_SECRET = re.compile(r"(^|[_.-])(token|code|key|apikey|secret|sig|signature|auth|authuser|password|pass|passwd|session|"
                     r"sessionid|sid|otp|nonce|ticket|jwt|credential|hash)$", re.IGNORECASE)


def clean_url(url: str) -> str:
    """The address without the parts that look like keys or tracking, so it is safe to show and to keep."""
    try:
        u = urlsplit(url)
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
         if not _SECRET.search(k) and not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    frag = u.fragment
    if "=" in frag and any(_SECRET.search(k) for k, _ in parse_qsl(frag, keep_blank_values=True)):
        frag = ""
    netloc = u.hostname or ""
    if u.port:
        netloc += f":{u.port}"                           # never a user name or password in what kb shows
    return urlunsplit((u.scheme, netloc, u.path, urlencode(q), frag))


def host(url: str) -> str:
    try:
        h = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return h.removeprefix("www.")


def _on(h: str, names) -> bool:
    return any(h == n or h.endswith("." + n) for n in names)


def search_words(url: str) -> str | None:
    """What you searched for, when the address is a search page."""
    h, u = host(url), urlsplit(url)
    for engine, paths in SEARCH.items():
        on = h.startswith("google.") if engine == "google" else _on(h, (engine,))
        if on and u.path in paths:
            q = dict(parse_qsl(u.query))
            return (q.get("q") or q.get("text") or "").strip() or None
    return None


def kind_of(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        return None
    h = host(url)
    if not h or _on(h, SKIP_HOSTS) or h.endswith(".ts.net"):
        return None                                       # kb's own pages, sign-in pages
    if _on(h, AI) or (h == "huggingface.co" and urlsplit(url).path.startswith("/chat")):
        return "ai"
    if search_words(url):
        return "search"
    if _on(h, DOCS):
        return "doc"
    return "web"


def local(ts: float) -> datetime:
    """A moment as the clock on this laptop shows it."""
    return datetime.fromtimestamp(ts, timezone.utc).astimezone()


def since(days: int, now: float) -> float:
    """Midnight on this laptop, days - 1 days before now: 1 is today, 2 is since yesterday."""
    d = local(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=max(1, days) - 1)).timestamp()


def _copy_read(db: Path, sql: str, args: tuple) -> list[tuple]:
    if db.stat().st_size > MAX_DB:
        raise OSError("too big to read")
    with tempfile.TemporaryDirectory(prefix="kb-where-") as tmp:
        copy = Path(tmp) / "h.sqlite"
        shutil.copyfile(db, copy)
        for extra in ("-wal", "-journal"):
            side = Path(str(db) + extra)
            if side.exists():
                shutil.copyfile(side, Path(str(copy) + extra))
        con = sqlite3.connect(copy)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()


# Where else kb looks when a browser is not in the lists above: snap and flatpak installs (Brave, Chromium, Opera
# from the Snap Store), and browsers that keep their own folder (Zen, LibreWolf, Floorp, Waterfox, Yandex ...).
LOOK_IN = (".config", "snap", ".var/app", ".local/share")
NOT_BROWSERS = {".cache", ".local", ".config", ".var", ".npm", ".cargo", ".rustup", ".nvm", ".pyenv", ".conda", ".ollama",
                ".docker", ".gradle", ".m2", ".vscode", ".vscode-server", ".cursor", ".git", ".gnupg", ".ssh", ".steam",
                ".wine", ".java", ".android", ".pki", ".icons", ".themes", ".fonts", ".kb"}
HEAVY = {"Cache", "Code Cache", "GPUCache", "Service Worker", "IndexedDB", "Extensions", "File System", "blob_storage",
         "cache2", "storage", "node_modules", "__pycache__", "site-packages", "Crashpad", "ShaderCache", "GrShaderCache",
         "optimization_guide_model_store", "Safe Browsing", "WidevineCdm", "Dictionaries", "component_crx_cache"}
NAMES = (("brave", "Brave"), ("vivaldi", "Vivaldi"), ("opera", "Opera"), ("edge", "Edge"), ("yandex", "Yandex"),
         ("thorium", "Thorium"), ("chromium", "Chromium"), ("chrome", "Chrome"), ("librewolf", "LibreWolf"),
         ("floorp", "Floorp"), ("waterfox", "Waterfox"), ("zen", "Zen"), ("firefox", "Firefox"), ("mozilla", "Firefox"))


def _sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _name(path: Path, home: Path) -> str:
    rel = path.relative_to(home)
    low = str(rel).lower()
    name = next((n for k, n in NAMES if k in low), rel.parts[0].lstrip(".") or "browser")
    prof = path.parent.name
    return f"{name} ({prof})" if prof.startswith("Profile ") else name


def find_histories(home: Path, budget: float = 2.0, max_seen: int = 200_000) -> list[tuple[str, Path, str]]:
    """Every browser history file in your home folder's hidden places, wherever the browser keeps it."""
    roots = [home / x for x in LOOK_IN]
    try:
        roots += [e for e in home.iterdir() if e.name.startswith(".") and e.name not in NOT_BROWSERS and e.is_dir()
                  and not e.is_symlink()]
    except OSError:
        pass
    t0, seen, out = time.monotonic(), 0, []
    stack = [(r, 0) for r in roots if r.is_dir()]
    while stack and seen < max_seen and time.monotonic() - t0 < budget:
        top, depth = stack.pop()
        try:
            entries = list(os.scandir(top))
        except OSError:
            continue
        for e in entries:
            seen += 1
            try:
                if e.is_dir(follow_symlinks=False):
                    if depth < 8 and e.name not in HEAVY:
                        stack.append((Path(e.path), depth + 1))
                elif e.is_file(follow_symlinks=False) and e.name in ("History", "places.sqlite"):
                    path = Path(e.path)
                    if _sqlite(path):
                        out.append((_name(path, home), path, "chrome" if e.name == "History" else "firefox"))
            except OSError:
                continue
    return out


def history_files(home: Path) -> list[tuple[str, Path, str]]:
    """(browser, history file, "chrome" or "firefox") for every profile found."""
    out = []
    for name, bases in CHROMES.items():
        for b in bases:
            base = home / b
            if not base.is_dir():
                continue
            for h in sorted([base / "History", *base.glob("*/History")]):
                if h.is_file():
                    prof = h.parent.name if h.parent != base else ""
                    out.append((f"{name} ({prof})" if prof and prof != "Default" else name, h, "chrome"))
    for b in FIREFOXES:
        base = home / b
        if base.is_dir():
            for p in sorted(base.glob("*/places.sqlite")):
                out.append(("Firefox", p, "firefox"))
    have = {os.path.realpath(p) for _, p, _ in out}
    for name, p, kind in find_histories(home):
        if os.path.realpath(p) not in have:
            have.add(os.path.realpath(p))
            out.append((name, p, kind))
    return out


def visits(home: Path, start: float, limit: int = 50_000) -> tuple[list[dict], list[str], list[str]]:
    """Every page visit since start, from every browser: (visits, browsers read, problems)."""
    got, read, problems = [], [], []
    for name, path, kind in history_files(home):
        try:
            if kind == "chrome":                         # microseconds since 1601-01-01
                rows = _copy_read(path, "SELECT u.url, u.title, v.visit_time FROM visits v JOIN urls u ON u.id = v.url "
                                  "WHERE v.visit_time >= ? ORDER BY v.visit_time DESC LIMIT ?",
                                  (int((start + 11_644_473_600) * 1_000_000), limit))
                rows = [(u, t, vt / 1_000_000 - 11_644_473_600) for u, t, vt in rows]
            else:                                         # microseconds since 1970
                rows = _copy_read(path, "SELECT p.url, p.title, h.visit_date FROM moz_historyvisits h JOIN moz_places p "
                                  "ON p.id = h.place_id WHERE h.visit_date >= ? ORDER BY h.visit_date DESC LIMIT ?",
                                  (int(start * 1_000_000), limit))
                rows = [(u, t, vd / 1_000_000) for u, t, vd in rows]
        except (OSError, sqlite3.Error) as e:
            problems.append(f"{name}: {e}")
            continue
        read.append(name)
        got += [{"url": u or "", "title": t or "", "ts": float(ts), "browser": name} for u, t, ts in rows]
    return got, read, problems


def pages(vs: list[dict]) -> list[dict]:
    """Visits as pages: one line per address, with its newest time and how many times you opened it."""
    seen: dict[str, dict] = {}
    for v in sorted(vs, key=lambda x: x["ts"], reverse=True):
        url = v["url"]
        if url.startswith("file://"):
            path = unquote(urlsplit(url).path)
            key = "file:" + path
            if key not in seen:
                seen[key] = {"kind": "opened", "title": Path(path).name or path, "where": path, "ts": v["ts"],
                             "count": 0, "via": v["browser"]}
            seen[key]["count"] += 1
            continue
        k = kind_of(url)
        if not k:
            continue
        clean = clean_url(url)
        if clean not in seen:
            words = search_words(url)
            seen[clean] = {"kind": k, "title": words if k == "search" else (v["title"].strip() or clean),
                           "where": clean, "ts": v["ts"], "count": 0, "via": v["browser"]}
        seen[clean]["count"] += 1
    return list(seen.values())


def _iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def opened(home: Path, start: float) -> tuple[list[dict], list[str]]:
    """The files the desktop says you opened since start: (files, problems)."""
    out, problems = [], []
    xbel = home / ".local/share/recently-used.xbel"
    if xbel.is_file():
        try:
            if xbel.stat().st_size > MAX_XBEL:
                raise OSError("too big to read")
            ns = "{http://www.freedesktop.org/standards/desktop-bookmarks}"
            for bm in ET.parse(xbel).getroot().iter("bookmark"):
                href = bm.get("href") or ""
                if not href.startswith("file://"):
                    continue
                times = [_iso(bm.get(a)) for a in ("added", "modified", "visited")]
                apps = list(bm.iter(f"{ns}application"))
                times += [_iso(a.get("modified")) for a in apps]
                ts = max([t for t in times if t] or [0])
                if ts < start:
                    continue
                path = unquote(urlsplit(href).path)
                names = sorted({a.get("name") or "" for a in apps} - {""})
                out.append({"kind": "opened", "title": Path(path).name or path, "where": path, "ts": ts, "count": 1,
                            "via": ", ".join(names), "gone": not os.path.exists(path)})
        except (OSError, ET.ParseError) as e:
            problems.append(f"recently-used.xbel: {e}")
    kde = home / ".local/share/RecentDocuments"
    if kde.is_dir():
        for d in kde.glob("*.desktop"):
            try:
                ts = d.stat().st_mtime
                if ts < start:
                    continue
                url = next((x[4:].strip() for x in d.read_text(encoding="utf-8", errors="replace").splitlines()
                            if x.startswith("URL=")), "")
            except OSError:
                continue
            path = unquote(urlsplit(url).path) if url.startswith("file://") else url
            if path.startswith("/"):
                out.append({"kind": "opened", "title": Path(path).name, "where": path, "ts": ts, "count": 1,
                            "via": "KDE", "gone": not os.path.exists(path)})
    return out, problems


def changed(roots: list[Path], start: float, skip: list[Path] = (), budget: float = 4.0, cap: int = 2000,
            max_seen: int = 400_000) -> tuple[list[dict], bool]:
    """Files under roots changed since start, newest first: (files, stopped early)."""
    skip = {os.path.realpath(s) for s in skip}
    t0, seen, out, stopped = time.monotonic(), 0, [], False
    stack = [(str(r), 0) for r in roots if r.is_dir()]
    while stack:
        top, depth = stack.pop()
        try:
            it = os.scandir(top)
        except OSError:
            continue
        with it:
            for e in it:
                seen += 1
                if seen > max_seen or time.monotonic() - t0 > budget:
                    stopped = True
                    stack = []
                    break
                name = e.name
                if name.startswith(".") or name in SKIP_DIRS:
                    continue
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir():
                        if depth < 12 and os.path.realpath(e.path) not in skip:
                            stack.append((e.path, depth + 1))
                        continue
                    if name.endswith(NOISE) or name.startswith("~$"):
                        continue
                    st = e.stat()
                except OSError:
                    continue
                if st.st_mtime >= start:
                    out.append({"kind": "changed", "title": name, "where": e.path, "ts": st.st_mtime, "count": 1,
                                "size": st.st_size})
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out[:cap], stopped


def gather(days: int = 2, home: str | Path | None = None, now: float | None = None, skip: list[Path] = (),
           budget: float = 4.0) -> dict:
    """Everything kb can see of where you were since the start of the day, days - 1 days ago."""
    home = Path(home or os.path.expanduser("~"))
    now = time.time() if now is None else now
    start = since(days, now)
    vs, browsers, problems = visits(home, start)
    items = pages(vs)
    files, p2 = opened(home, start)
    have = {x["where"] for x in items if x["kind"] == "opened"}
    items += [f for f in files if f["where"] not in have]
    ch, stopped = changed([home], start, skip, budget)
    items += ch
    items = [x for x in items if x["ts"] <= now + 60]
    items.sort(key=lambda x: x["ts"], reverse=True)
    return {"days": days, "since": start, "now": now, "items": items, "browsers": browsers,
            "problems": problems + p2, "stopped": stopped, "budget": budget, "home": str(home)}


def counts(items: list[dict]) -> dict[str, int]:
    return {k: sum(x["kind"] == k for x in items) for k in KINDS}


def find(items: list[dict], words: str) -> list[dict]:
    """The lines that hold every word, in any case."""
    ws = [w for w in words.casefold().split() if w]
    return [x for x in items if all(w in f"{x['title']} {x['where']}".casefold() for w in ws)]


def folders(items: list[dict], home: str = "") -> list[dict]:
    """Changed files grouped by folder, the folder with the newest change first."""
    groups: dict[str, dict] = {}
    for x in items:
        if x["kind"] != "changed":
            continue
        d = os.path.dirname(x["where"])
        g = groups.setdefault(d, {"folder": d, "files": [], "ts": x["ts"]})
        g["files"].append(x)
        g["ts"] = max(g["ts"], x["ts"])
    return sorted(groups.values(), key=lambda g: g["ts"], reverse=True)


def short(path: str, home: str) -> str:
    return "~" + path[len(home):] if home and (path == home or path.startswith(home.rstrip("/") + "/")) else path


def when(ts: float, now: float, words: tuple[str, str] = ("today", "yesterday")) -> str:
    d, n = local(ts), local(now)
    if d.date() == n.date():
        return f"{words[0]} {d:%H:%M}"
    if d.date() == (n - timedelta(days=1)).date():
        return f"{words[1]} {d:%H:%M}"
    return f"{d:%Y-%m-%d %H:%M}"


TITLES = {"ai": "AI chats", "search": "Searches", "doc": "Documents and research", "opened": "Files you opened",
          "changed": "Files you changed", "web": "Other pages"}


def md(data: dict, words: str | None = None, per: int = 40) -> str:
    """What kb where prints."""
    items = find(data["items"], words) if words else data["items"]
    c = counts(items)
    start = local(data["since"])
    lines = [f"# Where you were since {start:%Y-%m-%d %H:%M}" + (f', lines with "{words}"' if words else ""), "",
             " ".join(f"{TITLES[k]}: {c[k]}." for k in KINDS)]
    if data["browsers"]:
        lines.append("Browsers read: " + ", ".join(data["browsers"]) + ".")
    for p in data["problems"]:
        lines.append(f"Could not read {p}")
    if data["stopped"]:
        lines.append(f"Your home folder is big, so kb stopped looking for changed files after {data['budget']:g} "
                     "seconds. Some may be missing.")
    for k in KINDS:
        rows = [x for x in items if x["kind"] == k]
        if not rows:
            continue
        lines += ["", f"## {TITLES[k]}"]
        if k == "changed":
            for g in folders(rows)[:per]:
                names = ", ".join(f["title"] for f in g["files"][:6]) + (" ..." if len(g["files"]) > 6 else "")
                lines.append(f"- {when(g['ts'], data['now'])}  {short(g['folder'], data['home'])}  "
                             f"({len(g['files'])}): {names}")
            continue
        for x in rows[:per]:
            where = short(x["where"], data["home"]) if k == "opened" else x["where"]
            lines.append(f"- {when(x['ts'], data['now'])}  {x['title']}")
            lines.append(f"   {where}")
        if len(rows) > per:
            lines.append(f"- and {len(rows) - per} more")
    return "\n".join(lines) + "\n"
