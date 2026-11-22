"""kb serve: your advice runs as pages on this machine, with Save buttons in place of commands to paste.

It listens on 127.0.0.1 only, so nothing on your network or the internet can reach it. To open it on your phone,
put Tailscale in front of it (``tailscale serve``): that shows it to your own devices on your tailnet and to nobody
else. Never put it behind a public tunnel (Tailscale Funnel, ngrok, a router port): the pages hold your private cards.

What it guards against, since a page in your own browser could try to talk to it:
- a request must name this machine (127.0.0.1, localhost) or your tailnet (a name ending in .ts.net) as its Host,
  which stops a web page from reaching it through a renamed address (DNS rebinding);
- a change must be a JSON POST carrying the header X-KB: 1, which a page from another site cannot send without
  asking first, and kb never says yes; an Origin header, when there is one, must be this same address;
- bodies are small, and every page says no to frames, referrers and outside resources.

Ratings, picks and lessons go through the same code as the command line, so the rules are the same.
"""

from __future__ import annotations

import html
import json
import re
import sys
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import theme
from ..runlog import RunLog, query
from . import lessons as les
from . import page, rating

MAX_BODY = 64_000
RUN = re.compile(r"^/run/(run_[0-9A-Za-z]{6,32})$")
CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
LOCAL = {"127.0.0.1", "localhost", "[::1]"}

LABELS = {
    "en": {
        "title": "Your advice runs",
        "sub": "Served by kb on this laptop. Only this laptop, and your own devices through Tailscale, can open it.",
        "via": "Opened as {who} through your tailnet.",
        "runs_h": "Runs", "none": "No advice run yet. Make one on the laptop with: kb picture advise",
        "rated": "rated {r} of {n}", "not_rated": "not rated yet", "picked": "picked {w}", "failed": "failed",
        "nobody": "no answer", "lessons_h": "Your lessons",
        "lessons_note": "Every advice run follows them. Add one in your own words; it counts from the next run.",
        "no_lessons": "No lessons yet.", "add": "Add lesson", "lesson_ph": "A rule for kb's advice, in your own words",
        "saving": "Saving…", "not_saved": "Not saved: {e}", "other": "العربية", "other_lang": "ar",
        "private": "Private: these pages hold lines from your cards. kb serve shows them only to you.",
    },
    "ar": {
        "title": "تشغيلات النصائح",
        "sub": "يعرضها kb من هذا اللابتوب. لا يفتحها إلا هذا اللابتوب وأجهزتك أنت عبر Tailscale.",
        "via": "فُتحت باسم {who} عبر شبكتك الخاصة.",
        "runs_h": "التشغيلات", "none": "لا يوجد تشغيل نصائح بعد. أنشئ واحدًا على اللابتوب بالأمر: kb picture advise",
        "rated": "التقييم: {r} من {n}", "not_rated": "لم يُقيَّم بعد", "picked": "الاختيار: {w}", "failed": "فشل",
        "nobody": "لا إجابة", "lessons_h": "دروسك",
        "lessons_note": "كل تشغيل نصائح يتبعها. أضف درسًا بكلماتك، ويُحسب من التشغيل التالي.",
        "no_lessons": "لا دروس بعد.", "add": "أضف الدرس", "lesson_ph": "قاعدة لنصائح kb بكلماتك",
        "saving": "جارٍ الحفظ…", "not_saved": "لم يُحفظ: {e}", "other": "English", "other_lang": "en",
        "private": "خاص: هذه الصفحات تحمل سطورًا من بطاقاتك، ولا يعرضها kb serve إلا لك.",
    },
}


def _t(lang: str, key: str, **v) -> str:
    s = LABELS[lang][key]
    for k, x in v.items():
        s = s.replace("{" + k + "}", f"\u2068{x}\u2069" if lang == "ar" else str(x))
    return s


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def host_ok(host: str | None, port: int) -> bool:
    """This machine by name or number, on our port, or a name on your tailnet (tailscale serve keeps the Host)."""
    if not host:
        return False
    host = host.strip().lower()
    name, _, p = host.rpartition(":") if not host.endswith("]") else (host, "", "")
    if not name:                        # no port given
        name, p = host, ""
    if name in LOCAL:
        return p == str(port)
    return name.endswith(".ts.net") and p in ("", "443")


def _changes(raw) -> list[tuple[int, str, bool]]:
    """Your changes to pieces as the page sends them: [{"n": 2, "text": "...", "lesson": true}, ...]."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 50:
        raise KeyError("changes must be a short list.")
    out = []
    for c in raw:
        if not (isinstance(c, dict) and isinstance(c.get("n"), int) and not isinstance(c.get("n"), bool)
                and isinstance(c.get("text"), str) and isinstance(c.get("lesson", False), bool)):
            raise KeyError("each change needs a piece number n, its text, and lesson true or false.")
        out.append((c["n"], c["text"], c.get("lesson", False)))
    return out


def verdicts(log: RunLog) -> dict[str, dict]:
    """For each advice run: how many models answered, how many answers you rated, and whom you picked."""
    out: dict[str, dict] = {}
    for r in log.db.execute("""
            SELECT s.run_id, s.id, s.worker,
                   EXISTS(SELECT 1 FROM scores c WHERE c.step_id = s.id AND c.name = 'would_act') AS rated,
                   (SELECT c.value FROM scores c WHERE c.step_id = s.id AND c.name = 'picked' ORDER BY c.id DESC LIMIT 1) AS picked
            FROM steps s JOIN runs r ON r.id = s.run_id
            WHERE r.task = 'advise' AND s.name = 'advise' AND s.status = 'ok' AND s.worker IS NOT NULL"""):
        x = out.setdefault(r["run_id"], {"answers": 0, "rated": 0, "picked": None})
        x["answers"] += 1
        x["rated"] += r["rated"]
        if r["picked"] == 1.0:
            x["picked"] = r["worker"]
    return out


INDEX_CSS = """
:root{--bg:#f4f1ea;--ink:#1d2430;--soft:#5b6472;--line:#d9d3c6;--card:#fffdf8;--accent:#0b6bcb;--warn:#b45309;--ok:#15803d}
@media (prefers-color-scheme: dark){:root{--bg:#10151d;--ink:#e8ecf2;--soft:#9aa6b6;--line:#2a3340;--card:#171e29;--accent:#6cb6ff;--warn:#fbbf24;--ok:#4ade80}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans","Noto Naskh Arabic","Geeza Pro",Tahoma,sans-serif}
button,textarea{font:inherit;color:inherit}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:clamp(1.5rem,5vw,2rem);line-height:1.15;margin:0 0 4px}
h2{font-size:1.15rem;margin:0 0 8px}
p{margin:0 0 6px}
.soft{color:var(--soft)}
.small{font-size:.9rem}
.top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.top a{color:var(--accent);white-space:nowrap}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:14px 0}
.runs{list-style:none;margin:0;padding:0}
.runs li{border-top:1px solid var(--line)}
.runs li:first-child{border-top:0}
.runs a{display:flex;flex-wrap:wrap;gap:2px 12px;align-items:baseline;padding:12px 4px;min-height:48px;color:inherit;text-decoration:none}
.runs a:hover .who,.runs a:focus-visible .who{text-decoration:underline}
.date{font-weight:600}
.who{color:var(--accent);font-weight:600}
.state{color:var(--soft);font-size:.92rem;margin-inline-start:auto}
.state.todo{color:var(--warn);font-weight:600}
.state.done{color:var(--ok)}
.lessons{margin:8px 0 12px;padding-inline-start:22px}
.lessons li{margin:0 0 4px}
textarea{width:100%;min-height:84px;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px;resize:vertical}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px}
button{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:0 18px;min-height:44px;cursor:pointer;font-weight:600}
@media (prefers-color-scheme: dark){button{color:#06121f}}
button:disabled{opacity:.6;cursor:default}
.err{color:var(--warn)}
footer{color:var(--soft);font-size:.86rem;margin-top:20px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""

INDEX_JS = """
(function(){
"use strict";
var L = JSON.parse(document.getElementById("data").textContent);
var b = document.getElementById("add"), t = document.getElementById("lesson"), say = document.getElementById("say");
function ready(){ b.disabled = !t.value.trim(); }
t.addEventListener("input", ready); ready();
b.addEventListener("click", function(){
  b.disabled = true; b.textContent = L.saving; say.textContent = ""; say.className = "";
  fetch("/api/lesson", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"},
                        body: JSON.stringify({text: t.value})})
    .then(function(r){ return r.json().then(function(j){ return {ok: r.ok, j: j}; }); })
    .then(function(x){ if (!x.ok) throw new Error(x.j.error || "?"); location.reload(); })
    .catch(function(e){ b.textContent = L.add; ready(); say.textContent = L.not_saved.replace("{e}", e.message); say.className = "err"; });
});
})();
"""


def index(log: RunLog | None, lessons: list[str], lang: str = "en", who: str | None = None, limit: int = 60,
          today: date | None = None) -> str:
    """The first page: every advice run, newest first, with what you have recorded, and your lessons."""
    lang = lang if lang in LABELS else "en"
    runs = query.runs(log, task="advise", limit=limit) if log else []
    seen = verdicts(log) if log else {}
    items = []
    for r in runs:
        v = seen.get(r["id"], {"answers": 0, "rated": 0, "picked": None})
        if r["status"] == "failed" and not v["answers"]:
            state, cls = _t(lang, "failed"), "state"
        elif not v["answers"]:
            state, cls = _t(lang, "nobody"), "state"
        elif v["rated"] < v["answers"]:
            state, cls = _t(lang, "rated", r=v["rated"], n=v["answers"]) if v["rated"] else _t(lang, "not_rated"), "state todo"
        else:
            state, cls = _t(lang, "rated", r=v["rated"], n=v["answers"]), "state done"
        if v["picked"]:
            state += " · " + _t(lang, "picked", w=v["picked"])
        items.append(f'<li><a href="/run/{_e(r["id"])}?lang={lang}"><span class="date">{_e(r["started"][:10])}</span>'
                     f'<span class="who"><bdi>{_e(", ".join((r["label"] or "-").split(",")))}</bdi></span><span class="{cls}">{_e(state)}</span></a></li>')
    runs_html = f'<ul class="runs">{"".join(items)}</ul>' if items else f'<p class="soft">{_e(_t(lang, "none"))}</p>'
    lesson_html = ('<ol class="lessons">' + "".join(f'<li><bdi>{_e(x)}</bdi></li>' for x in lessons) + "</ol>"
                   if lessons else f'<p class="soft">{_e(_t(lang, "no_lessons"))}</p>')
    via = f'<p class="soft small">{_e(_t(lang, "via", who=who))}</p>' if who else ""
    hud = theme.hud(theme.standing(page.history(log, limit=1_000_000) if log else [], today), lang)
    blob = json.dumps({k: LABELS[lang][k] for k in ("add", "saving", "not_saved")}, ensure_ascii=False).replace("<", "\\u003c")
    return theme.inject(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">'
            f'<title>{_e(_t(lang, "title"))}</title><style>{INDEX_CSS}</style></head><body><div class="wrap">'
            f'<header><div class="top"><h1>{_e(_t(lang, "title"))}</h1><a href="/?lang={LABELS[lang]["other_lang"]}" '
            f'lang="{LABELS[lang]["other_lang"]}">{_e(LABELS[lang]["other"])}</a></div>'
            f'<p class="soft">{_e(_t(lang, "sub"))}</p>{via}{hud}</header>'
            f'<section class="box"><h2>{_e(_t(lang, "runs_h"))}</h2>{runs_html}</section>'
            f'<section class="box"><h2>{_e(_t(lang, "lessons_h"))} ({len(lessons)})</h2>'
            f'<p class="soft small">{_e(_t(lang, "lessons_note"))}</p>{lesson_html}'
            f'<textarea id="lesson" dir="auto" maxlength="600" placeholder="{_e(_t(lang, "lesson_ph"))}" '
            f'aria-label="{_e(_t(lang, "lesson_ph"))}"></textarea>'
            f'<div class="row"><button type="button" id="add">{_e(_t(lang, "add"))}</button><span id="say" role="status"></span></div></section>'
            f'<footer><p>{_e(_t(lang, "private"))}</p></footer></div>'
            f'<script id="data" type="application/json">{blob}</script><script>{INDEX_JS}</script></body></html>')


class Kb:
    """What the server needs: where the run log and the lessons are, and its own port."""

    def __init__(self, runlog: str | Path, lessons: str | Path, port: int, lang: str = "en", today: date | None = None):
        self.runlog, self.lessons, self.port, self.lang, self.today = Path(runlog), Path(lessons), port, lang, today

    def log(self) -> RunLog | None:
        return RunLog(self.runlog) if self.runlog.exists() else None


class Handler(BaseHTTPRequestHandler):
    kb: Kb
    server_version = "kb"
    sys_version = ""

    def log_message(self, fmt, *args):                    # one quiet line per request, no addresses or bodies
        sys.stderr.write(f"  {self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    def _send(self, code: int, body: str, kind: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _lang(self) -> str:
        lang = (parse_qs(urlsplit(self.path).query).get("lang") or [self.kb.lang])[0]
        return lang if lang in LABELS else self.kb.lang

    def _guard(self) -> bool:
        if not host_ok(self.headers.get("Host"), self.kb.port):
            self._send(421, "kb serve answers only to this machine and to your own tailnet name (ending in .ts.net).",
                       "text/plain; charset=utf-8")
            return False
        return True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard():
            return
        path, lang = urlsplit(self.path).path, self._lang()
        try:
            if path == "/":
                log = self.kb.log()
                try:
                    body = index(log, les.read(self.kb.lessons), lang, self.headers.get("Tailscale-User-Login"),
                                 today=self.kb.today)
                finally:
                    if log:
                        log.close()
                return self._send(200, body)
            m = RUN.match(path)
            if m:
                log = self.kb.log()
                if not log:
                    return self._send(404, "No run log yet.", "text/plain; charset=utf-8")
                try:
                    run_id = log.get(m.group(1)).id
                    data = page.gather(log, run_id)
                    hist = page.history(log)
                    record = theme.standing(page.history(log, limit=1_000_000), self.kb.today)
                finally:
                    log.close()
                return self._send(200, page.build(data, hist, lang=lang, today=self.kb.today, live=True, record=record))
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return None
            return self._send(404, "Not here. Your runs are at /", "text/plain; charset=utf-8")
        except KeyError as e:
            return self._send(404, str(e.args[0]), "text/plain; charset=utf-8")
        except Exception as e:                                # noqa: BLE001 - say what broke, keep serving
            traceback.print_exc()
            return self._send(500, f"kb hit an error: {type(e).__name__}: {e}", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._guard():
            return None
        path = urlsplit(self.path).path
        if self.headers.get("X-KB") != "1":
            return self._json(403, {"error": "kb takes changes only from its own pages."})
        origin = urlsplit(self.headers.get("Origin") or "").netloc.lower()
        if origin and origin != (self.headers.get("Host") or "").lower() and not host_ok(origin, self.kb.port):
            # a proxy may pass the Host on or rewrite it to 127.0.0.1; either way the page must come from here
            return self._json(403, {"error": "kb takes changes only from its own pages."})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "send JSON."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            return self._json(413, {"error": f"too long; kb takes up to {MAX_BODY} bytes."})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self._json(400, {"error": "that was not a JSON object."})
        try:
            if path == "/api/lesson":
                text = str(body.get("text") or "")
                have, new = les.add(self.kb.lessons, text, self.kb.today or date.today())
                return self._json(200, {"ok": True, "new": new, "lessons": len(have)})
            if path not in ("/api/rate", "/api/pick"):
                return self._json(404, {"error": "no such action."})
            log = self.kb.log()
            if not log:
                return self._json(404, {"error": f"no run log at {self.kb.runlog}."})
            try:
                if path == "/api/rate":
                    pieces = body.get("pieces") or []
                    if not isinstance(pieces, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in pieces):
                        raise KeyError("pieces must be a list of piece numbers.")
                    changes = _changes(body.get("changes"))
                    r = rating.rate(log, str(body.get("run") or ""), pieces, str(body.get("worker") or "") or None,
                                    str(body.get("why") or "") or None, changes=[(k, t) for k, t, _ in changes],
                                    kept=[k for k, _, keep in changes if keep])
                    r["lessons_added"] = [les.add(self.kb.lessons, t, self.kb.today or date.today())[1]
                                          for k, t in r["changes"] if k in r["kept"]].count(True)
                else:
                    r = rating.pick(log, str(body.get("run") or ""), str(body.get("worker") or ""))
            finally:
                log.close()
            return self._json(200, {"ok": True, **r})
        except KeyError as e:
            return self._json(400, {"error": str(e.args[0])})
        except Exception as e:                                # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


def make(kb: Kb) -> ThreadingHTTPServer:
    """A server bound to 127.0.0.1 only. Call serve_forever() on it; port 0 picks a free port (for tests)."""
    handler = type("KbHandler", (Handler,), {"kb": kb})
    srv = ThreadingHTTPServer(("127.0.0.1", kb.port), handler)
    srv.daemon_threads = True
    if kb.port == 0:
        kb.port = srv.server_address[1]
    return srv
