"""kb serve: your advice runs as pages on this machine, with Save buttons in place of commands to paste.

It listens on 127.0.0.1 only, so nothing on your network or the internet can reach it. To open it on your phone,
put Tailscale in front of it (``tailscale serve``): that shows it to your own devices on your tailnet and to nobody
else. Never put it behind a public tunnel (Tailscale Funnel, ngrok, a router port): the pages hold your private cards.

What it guards against, since a page in your own browser could try to talk to it:
- a request must name this machine (127.0.0.1, localhost) or your tailnet (a name ending in .ts.net) as its Host,
  which stops a web page from reaching it through a renamed address (DNS rebinding);
- a change must be a JSON POST carrying the header X-KB: 1, which a page from another site cannot send without
  asking first, and kb never says yes; an Origin header, when there is one, must be this same address;
- bodies are small (the inbox takes files up to 20 MB each), and every page says no to frames, referrers and
  outside resources.

Ratings, picks, lessons and the inbox go through the same code as the command line, so the rules are the same. What
you send to the inbox stays on this machine: see picture/inbox.py.
"""

from __future__ import annotations

import base64
import binascii
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
from . import inbox as inb
from . import lessons as les
from . import page, rating

MAX_BODY = 64_000
MAX_INBOX_BODY = 30_000_000          # up to ten files a send, each up to inbox.MAX_FILE, sent as base64
SHORT_NOTE = 280                     # words sent with files and no longer than this are their note, not a post
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
        "inbox_h": "Your inbox",
        "inbox_note": "Paste a post or a link, attach screenshots, PDFs, Word files or voice notes, or record one. "
                      "It all stays on this laptop, and kb reads what it can here.",
        "inbox_ph": "Paste a post or a link, or write a few words. A few words sent with files become their note.",
        "attach": "Attach files", "record": "Record a voice note", "stop": "Stop recording",
        "send": "Send to kb", "sending": "Sending…", "sent": "Kept: {n}.", "again": "{n} already in your inbox.",
        "not_sent": "Not sent: {e}. Sending again is safe: kb keeps each thing once.",
        "remove": "Remove {name}", "too_big": "{name} is over 20 MB, so kb cannot keep it.",
        "no_mic": "No microphone: {e}", "inbox_empty": "Nothing here yet.",
        "inbox_more": "{n} items in all. On the laptop: kb inbox",
        "k_text": "text", "k_link": "link", "k_pdf": "PDF", "k_word": "Word", "k_slides": "slides",
        "k_image": "picture", "k_audio": "voice", "k_other": "file",
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
        "inbox_h": "صندوقك",
        "inbox_note": "الصق منشورًا أو رابطًا، أو أرفق لقطات شاشة وملفات PDF وWord ورسائل صوتية، أو سجّل واحدة. "
                      "كل شيء يبقى على هذا اللابتوب، ويقرأ kb ما يستطيع هنا.",
        "inbox_ph": "الصق منشورًا أو رابطًا، أو اكتب كلمات قليلة. الكلمات القليلة المرسلة مع ملفات تصير ملاحظتها.",
        "attach": "أرفق ملفات", "record": "سجّل رسالة صوتية", "stop": "أوقف التسجيل",
        "send": "أرسل إلى kb", "sending": "جارٍ الإرسال…", "sent": "حُفظ: {n}.", "again": "موجود من قبل في صندوقك: {n}.",
        "not_sent": "لم يُرسل: {e}. الإرسال مرة أخرى آمن: يحفظ kb كل شيء مرة واحدة.",
        "remove": "احذف {name}", "too_big": "{name} أكبر من 20 ميغابايت، فلا يحفظه kb.",
        "no_mic": "لا ميكروفون: {e}", "inbox_empty": "لا شيء هنا بعد.",
        "inbox_more": "عدد العناصر كلها: {n}. على اللابتوب: kb inbox",
        "k_text": "نص", "k_link": "رابط", "k_pdf": "PDF", "k_word": "Word", "k_slides": "شرائح",
        "k_image": "صورة", "k_audio": "صوت", "k_other": "ملف",
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
.wrap{max-width:1240px;margin:0 auto;padding:20px 16px 40px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:26px;align-items:start}
@media (max-width:900px){.layout{grid-template-columns:minmax(0,1fr);gap:0}}
h1{font-size:clamp(1.5rem,5vw,2rem);line-height:1.15;margin:0 0 4px}
h2{font-size:1.15rem;margin:0 0 8px}
p{margin:0 0 6px}
.soft{color:var(--soft)}
.small{font-size:.9rem}
.top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.top a{color:var(--accent);white-space:nowrap}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:0 0 22px}
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
.btn{background:var(--card);color:var(--ink);border:1.5px solid var(--line)}
.pending{list-style:none;margin:6px 0 0;padding:0}
.pending li{display:flex;gap:10px;align-items:center;justify-content:space-between;border-top:1px dashed var(--line);padding:4px 0}
.pending span{overflow-wrap:anywhere}
.pending .btn{min-height:40px;min-width:44px;padding:0 12px;font-size:1.1rem}
.inbox{list-style:none;margin:14px 0 0;padding:0}
.inbox li{display:grid;grid-template-columns:4.6em minmax(0,1fr);column-gap:10px;row-gap:2px;border-top:1px solid var(--line);padding:10px 2px}
.kind{grid-row:1/span 4;font-weight:700}
.what{grid-column:2;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;overflow:hidden}
.inbox .note{grid-column:2;font-size:.92rem;border-inline-start:3px solid var(--line);padding-inline-start:8px;margin:2px 0}
.meta{grid-column:2;display:flex;flex-wrap:wrap;gap:0 14px;color:var(--soft);font-size:.88rem}
.kept{color:var(--ok);font-weight:600}
.drop{outline:2px dashed var(--accent);outline-offset:4px}
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

var post = document.getElementById("post");
if (!post) return;
var box = document.getElementById("inbox"), pick = document.getElementById("pick"), attach = document.getElementById("attach"),
    rec = document.getElementById("rec"), send = document.getElementById("send"), said = document.getElementById("said"),
    list = document.getElementById("pending"), files = [], busy = false, recording = false;
function two(n){ return ("0" + n).slice(-2); }
function stamp(){ var d = new Date(); return d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate()) + "-" + two(d.getHours()) + two(d.getMinutes()); }
function size(n){ return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
function tell(m, c){ said.textContent = m; said.className = c || ""; }
function can(){ send.disabled = busy || recording || (!post.value.trim() && !files.length); }
function draw(){
  list.textContent = "";
  files.forEach(function(f, i){
    var li = document.createElement("li"), s = document.createElement("span"), x = document.createElement("button");
    s.textContent = f.name + " (" + size(f.blob.size) + ")";
    x.type = "button"; x.className = "btn"; x.textContent = "\\u00d7"; x.setAttribute("aria-label", L.remove.replace("{name}", f.name));
    x.addEventListener("click", function(){ files.splice(i, 1); draw(); });
    li.appendChild(s); li.appendChild(x); list.appendChild(li);
  });
  can();
}
function take(fl){
  for (var i = 0; i < fl.length; i++){
    var f = fl[i];
    if (f.size > L.max_file){ tell(L.too_big.replace("{name}", f.name), "err"); continue; }
    files.push({name: f.name || "pasted-" + stamp(), blob: f});
  }
  draw();
}
post.addEventListener("input", can);
attach.addEventListener("click", function(){ pick.click(); });
pick.addEventListener("change", function(){ take(pick.files); pick.value = ""; });
post.addEventListener("paste", function(e){
  var c = e.clipboardData;
  if (c && c.files && c.files.length){ take(c.files); if (!(c.getData("text") || "").trim()) e.preventDefault(); }
});
box.addEventListener("dragover", function(e){ e.preventDefault(); box.classList.add("drop"); });
box.addEventListener("dragleave", function(){ box.classList.remove("drop"); });
box.addEventListener("drop", function(e){ e.preventDefault(); box.classList.remove("drop"); if (e.dataTransfer) take(e.dataTransfer.files); });

var mr = null, chunks = [], t0 = 0, tick = null;
rec.addEventListener("click", function(){
  if (recording){ mr.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder){ tell(L.no_mic.replace("{e}", "this browser cannot record"), "err"); return; }
  navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream){
    var type = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"].filter(function(x){
      return MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(x); })[0];
    chunks = [];
    mr = type ? new MediaRecorder(stream, {mimeType: type}) : new MediaRecorder(stream);
    mr.ondataavailable = function(e){ if (e.data && e.data.size) chunks.push(e.data); };
    mr.onstop = function(){
      clearInterval(tick); recording = false; rec.setAttribute("aria-pressed", "false"); rec.textContent = L.record;
      stream.getTracks().forEach(function(k){ k.stop(); });
      var mt = mr.mimeType || type || "audio/webm", blob = new Blob(chunks, {type: mt});
      var ext = mt.indexOf("mp4") >= 0 ? ".m4a" : mt.indexOf("ogg") >= 0 ? ".ogg" : ".webm";
      if (blob.size){ blob.name = "voice-note-" + stamp() + ext; take([blob]); } else { can(); }
    };
    mr.start(1000); recording = true; t0 = Date.now(); rec.setAttribute("aria-pressed", "true");
    var show = function(){ var s = Math.floor((Date.now() - t0) / 1000);
      rec.textContent = L.stop + " " + Math.floor(s / 60) + ":" + two(s % 60); if (s >= 900) mr.stop(); };
    show(); tick = setInterval(show, 1000); can();
  }).catch(function(e){ tell(L.no_mic.replace("{e}", e.message || e.name), "err"); });
});

function b64(blob){ return new Promise(function(ok, no){ var r = new FileReader();
  r.onload = function(){ var s = String(r.result); ok(s.slice(s.indexOf(",") + 1)); };
  r.onerror = function(){ no(r.error || new Error("could not read the file")); }; r.readAsDataURL(blob); }); }
function one(body){
  return fetch("/api/inbox", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.error || String(r.status)); return j; }); });
}
send.addEventListener("click", function(){
  var text = post.value.trim(), jobs = [], note = "", kept = 0, again = 0, done = 0;
  if (text && (!files.length || text.length > L.short || /^https?:\\/\\/\\S+$/i.test(text))) jobs.push(function(){ return one({text: text}); });
  else note = text;
  files.forEach(function(f){ jobs.push(function(){ return b64(f.blob).then(function(d){ return one({name: f.name, data: d, note: note}); }); }); });
  busy = true; can(); send.textContent = L.sending; tell("");
  jobs.reduce(function(p, job){ return p.then(function(){ return job().then(function(j){
      if (j.new) kept++; else again++; done++; tell(done + " / " + jobs.length); }); }); }, Promise.resolve())
    .then(function(){ location.replace("/?lang=" + L.lang + "&kept=" + kept + "&again=" + again + "#inbox"); })
    .catch(function(e){ busy = false; send.textContent = L.send; can(); tell(L.not_sent.replace("{e}", e.message), "err"); });
});
})();
"""


def inbox_html(box: list[dict], lang: str, got: dict | None = None, show: int = 12) -> str:
    """The inbox box: paste, attach, record, send, then the newest items."""
    got = got or {}
    said = " ".join(x for x in (_t(lang, "sent", n=got["kept"]) if got.get("kept") else "",
                                _t(lang, "again", n=got["again"]) if got.get("again") else "") if x)
    rows = []
    for x in box[:show]:
        what = x.get("name") or x.get("preview") or "-"
        notes = "".join(f'<span class="note"><bdi>{_e(n["text"][:200])}</bdi></span>' for n in x.get("notes", [])[-2:])
        rows.append(f'<li><span class="kind">{_e(_t(lang, "k_" + x["kind"]))}</span><span class="what"><bdi>{_e(what)}</bdi></span>'
                    f'{notes}<span class="meta"><span>{_e(x["received"])}</span><span>{_e(inb.say(x, lang))}</span></span></li>')
    items = (f'<ul class="inbox">{"".join(rows)}</ul>' + (f'<p class="soft small">{_e(_t(lang, "inbox_more", n=len(box)))}</p>'
             if len(box) > show else "")) if rows else f'<p class="soft small">{_e(_t(lang, "inbox_empty"))}</p>'
    return (f'<section class="box" id="inbox"><h2>{_e(_t(lang, "inbox_h"))} ({len(box)})</h2>'
            f'<p class="soft small">{_e(_t(lang, "inbox_note"))}</p>'
            + (f'<p class="kept" role="status">{_e(said)}</p>' if said else "") +
            f'<textarea id="post" dir="auto" placeholder="{_e(_t(lang, "inbox_ph"))}" aria-label="{_e(_t(lang, "inbox_ph"))}"></textarea>'
            f'<input type="file" id="pick" multiple hidden>'
            f'<div class="row"><button type="button" class="btn" id="attach">{_e(_t(lang, "attach"))}</button>'
            f'<button type="button" class="btn" id="rec" aria-pressed="false">{_e(_t(lang, "record"))}</button></div>'
            f'<ul class="pending" id="pending" aria-live="polite"></ul>'
            f'<div class="row"><button type="button" id="send" disabled>{_e(_t(lang, "send"))}</button>'
            f'<span id="said" role="status"></span></div>{items}</section>')


def index(log: RunLog | None, lessons: list[str], lang: str = "en", who: str | None = None, limit: int = 60,
          today: date | None = None, box: list[dict] | None = None, got: dict | None = None) -> str:
    """The first page: your inbox, every advice run, newest first, with what you have recorded, and your lessons."""
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
    keys = ("add", "saving", "not_saved", "send", "sending", "not_sent", "record", "stop", "remove", "too_big", "no_mic")
    runs_box = f'<section class="box"><h2>{_e(_t(lang, "runs_h"))}</h2>{runs_html}</section>'
    lessons_box = (f'<section class="box"><h2>{_e(_t(lang, "lessons_h"))} ({len(lessons)})</h2>'
                   f'<p class="soft small">{_e(_t(lang, "lessons_note"))}</p>{lesson_html}'
                   f'<textarea id="lesson" dir="auto" maxlength="600" placeholder="{_e(_t(lang, "lesson_ph"))}" '
                   f'aria-label="{_e(_t(lang, "lesson_ph"))}"></textarea>'
                   f'<div class="row"><button type="button" id="add">{_e(_t(lang, "add"))}</button>'
                   f'<span id="say" role="status"></span></div></section>')
    # Wide like the advice page: the inbox takes the wide column, runs and lessons the narrow one. On a phone it is one
    # column, inbox first. Without an inbox the runs take the wide column.
    if box is not None:
        main, side = inbox_html(box, lang, got), runs_box + lessons_box
    else:
        main, side = runs_box, lessons_box
    blob = json.dumps({**{k: LABELS[lang][k] for k in keys}, "lang": lang, "short": SHORT_NOTE, "max_file": inb.MAX_FILE},
                      ensure_ascii=False).replace("<", "\\u003c")
    return theme.inject(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">'
            f'<title>{_e(_t(lang, "title"))}</title><style>{INDEX_CSS}</style></head><body><div class="wrap">'
            f'<header><div class="top"><h1>{_e(_t(lang, "title"))}</h1><a href="/?lang={LABELS[lang]["other_lang"]}" '
            f'lang="{LABELS[lang]["other_lang"]}">{_e(LABELS[lang]["other"])}</a></div>'
            f'<p class="soft">{_e(_t(lang, "sub"))}</p>{via}{hud}</header>'
            f'<div class="layout"><div class="main">{main}</div><div class="side">{side}</div></div>'
            f'<footer><p>{_e(_t(lang, "private"))}</p></footer></div>'
            f'<script id="data" type="application/json">{blob}</script><script>{INDEX_JS}</script></body></html>')


class Kb:
    """What the server needs: where the run log and the lessons are, and its own port."""

    def __init__(self, runlog: str | Path, lessons: str | Path, port: int, lang: str = "en", today: date | None = None,
                 inbox: str | Path | None = None):
        self.runlog, self.lessons, self.port, self.lang, self.today = Path(runlog), Path(lessons), port, lang, today
        self.inbox = inb.Inbox(inbox if inbox is not None else self.lessons.parent / "inbox")

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
                    q = parse_qs(urlsplit(self.path).query)
                    got = {k: int(v[0]) for k, v in q.items() if k in ("kept", "again") and v and v[0].isdigit()}
                    body = index(log, les.read(self.kb.lessons), lang, self.headers.get("Tailscale-User-Login"),
                                 today=self.kb.today, box=self.kb.inbox.items(), got=got)
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
        cap = MAX_INBOX_BODY if path == "/api/inbox" else MAX_BODY
        if n < 0 or n > cap:
            return self._json(413, {"error": f"too long; kb takes up to {cap:,} bytes here."})
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
            if path == "/api/inbox":
                return self._json(200, {"ok": True, **self._inbox(body)})
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


    def _inbox(self, body: dict) -> dict:
        """One item a request: {"text": ...} for a post or a link, or {"name", "data" (base64), "note"} for a file."""
        today = self.kb.today or date.today()
        data = body.get("data")
        if data is not None:
            if not isinstance(data, str):
                raise KeyError("data must be the file in base64.")
            try:
                raw = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                raise KeyError("data was not base64.") from None
            item = self.kb.inbox.add(raw, str(body.get("name") or "") or None, str(body.get("note") or "") or None,
                                     today, via="phone")
        else:
            item = self.kb.inbox.add_text(str(body.get("text") or ""), None, today, via="phone")
        return {k: item[k] for k in ("id", "kind", "status", "new", "name")}


def make(kb: Kb) -> ThreadingHTTPServer:
    """A server bound to 127.0.0.1 only. Call serve_forever() on it; port 0 picks a free port (for tests)."""
    handler = type("KbHandler", (Handler,), {"kb": kb})
    srv = ThreadingHTTPServer(("127.0.0.1", kb.port), handler)
    srv.daemon_threads = True
    if kb.port == 0:
        kb.port = srv.server_address[1]
    return srv
