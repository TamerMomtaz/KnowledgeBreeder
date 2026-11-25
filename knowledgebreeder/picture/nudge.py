"""Reminders on your phone: a morning note, and a reminder the day before and on the day of each deadline.

kb sends them through ntfy (https://ntfy.sh), a free notification service with an app for Android and iPhone. You
turn it on from the kb page. kb then makes a long random topic, the address your phone listens to, and keeps it in
work/nudge.json. Anyone who knew the topic could read the notes, so it is long and random, and kb never puts it in
your cards or the run log.

What leaves the laptop: short lines made from "Coming up" and "Where your work waits", nothing else. A line that holds
something private (your private list, #private, a phone number, an email, an amount of money, a key) is cut down to
its card's name, or to "a private item" when the card's name is private too. Nothing is sent while it is off.

The morning note goes once a day, at the first check between 08:00 and 14:00 on the laptop's clock, so a laptop that
wakes up late still sends it. Deadline reminders go from 08:00 to 22:00. Nothing goes at night. The laptop must be on
for anything to go.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from . import soon as soon_mod

SERVER = "https://ntfy.sh"
MORNING = 8                 # the first hour anything may go
MORNING_END = 14            # after this the morning note waits for the next day
QUIET = 22                  # from this hour nothing goes until the morning
KEEP_DAYS = 60              # how long kb remembers what it already sent

Post = Callable[[str, bytes, dict], None]

SAY = {
    "en": {"morning": "kb · good morning", "coming": "Coming up", "missed": "Slipped and still open",
           "waits": "Waiting on you: {n} needs on {c} cards.", "build": "Build on: {card}, quiet {d} days.",
           "nothing": "Nothing is due soon.", "due_0": "Due today", "due_1": "Due tomorrow", "private": "a private item",
           "test": "kb · test", "test_body": "Reminders from kb reach this phone.", "open": "Open kb"},
    "ar": {"morning": "kb · صباح الخير", "coming": "قريبًا", "missed": "فات موعده وما زال مفتوحًا",
           "waits": "ينتظرك: {n} حاجة على {c} بطاقة.", "build": "ابنِ على: {card}، هادئ منذ {d} يومًا.",
           "nothing": "لا شيء موعده قريب.", "due_0": "موعده اليوم", "due_1": "موعده غدًا", "private": "بند خاص",
           "test": "kb · تجربة", "test_body": "تصل تذكيرات kb إلى هذا الهاتف.", "open": "افتح kb"},
}


def _post(url: str, body: bytes, headers: dict) -> None:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:        # the address is ntfy's, or a server you set
        r.read()


class Nudge:
    """The reminder settings and what was already sent, kept in one small private file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def state(self) -> dict:
        try:
            s = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            s = {}
        if not isinstance(s, dict):
            s = {}
        return {"on": False, "server": SERVER, "topic": "", "sent": {}, "last": "", "error": "", "page": "",
                "lang": "en", **s}

    def _save(self, s: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".part")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def turn(self, on: bool, lang: str | None = None) -> dict:
        """On or off. The first time on, kb makes the topic; it stays the same after that, so the phone keeps it."""
        s = self.state()
        s["on"] = on
        if lang in SAY:
            s["lang"] = lang
        if on and not s["topic"]:
            s["topic"] = "kb-" + secrets.token_urlsafe(24).replace("_", "x").replace("-", "y")
        self._save(s)
        return s

    def remember_page(self, url: str) -> None:
        """The address the phone opens kb at, so a tap on a note opens kb."""
        s = self.state()
        if s["page"] != url:
            s["page"] = url
            self._save(s)

    def send(self, title: str, body: str, s: dict | None = None, priority: int = 3, tags: str = "",
             post: Post = _post) -> None:
        """One note, published as JSON so Arabic titles and lines travel as they are."""
        s = s or self.state()
        msg = {"topic": s["topic"], "title": title, "message": body, "priority": priority}
        if tags:
            msg["tags"] = [tags]
        if s.get("page"):
            msg["click"] = s["page"]
        post(s["server"].rstrip("/") + "/", json.dumps(msg, ensure_ascii=False).encode("utf-8"),
             {"Content-Type": "application/json"})

    def tick(self, now: datetime, rows: list[dict], waits: dict | None, private, lang: str | None = None,
             post: Post = _post) -> list[str]:
        """Send whatever is due now and was not sent before. Returns what was sent. Does nothing while off or at
        night."""
        s = self.state()
        if not s["on"] or not s["topic"] or not MORNING <= now.hour < QUIET:
            return []
        lang = lang or s["lang"]
        today = now.date()
        L = SAY.get(lang, SAY["en"])
        out: list[tuple[str, str, str, int, str]] = []
        key = f"morning:{today.isoformat()}"
        if key not in s["sent"] and now.hour < MORNING_END:
            out.append((key, L["morning"], morning(rows, waits, private, lang), 3, "sunrise"))
        for r in rows:
            if r["kind"] in ("deadline", "chance") and r["days"] in (0, 1):
                k = f'due:{r["id"] or "chance"}:{r["when"]}:{r["days"]}:{r["what"][:40]}'
                if k not in s["sent"]:
                    out.append((k, L[f'due_{r["days"]}'], line(r, private, lang, when=False), 4, "alarm_clock"))
        sent = []
        for k, title, body, prio, tags in out:
            try:
                self.send(title, body, s, prio, tags, post)
            except (urllib.error.URLError, OSError, ValueError) as e:
                s["error"] = f"{now:%Y-%m-%d %H:%M}: {type(e).__name__}: {getattr(e, 'reason', e)}"
                break
            s["sent"][k] = today.isoformat()
            s["last"], s["error"] = f"{now:%Y-%m-%d %H:%M} {title}", ""
            sent.append(k)
        cut = date.fromordinal(today.toordinal() - KEEP_DAYS).isoformat()
        s["sent"] = {k: v for k, v in s["sent"].items() if v >= cut}
        self._save(s)
        return sent


def line(r: dict, private, lang: str = "en", when: bool = True) -> str:
    """One Coming up row as a short line, with anything private cut down to its card's name."""
    L = SAY.get(lang, SAY["en"])
    card = r["card"] if r["card"] and not (private and private.holds(r["card"])) else ""
    what = r["what"] if not (private and private.holds(r["what"])) else ""
    if not what:
        what = L["private"]
    s = f"{card}: {what}" if card else what
    if when:
        d = date.fromisoformat(r["when"])
        s += f' ({soon_mod.when_words(r["days"], lang)}, {d.day}/{d.month})'
    return s


def morning(rows: list[dict], waits: dict | None, private, lang: str = "en", show: int = 4) -> str:
    """The morning note: what is close, what slipped, what waits on you, and one quiet thing to build on."""
    L = SAY.get(lang, SAY["en"])
    ahead = [r for r in rows if r["kind"] != "missed"]
    missed = [r for r in rows if r["kind"] == "missed"]
    out = []
    if ahead:
        out.append(L["coming"] + ":")
        out += ["• " + line(r, private, lang) for r in ahead[:show]]
    else:
        out.append(L["nothing"])
    if missed:
        out.append(L["missed"] + ":")
        out += ["• " + line(r, private, lang) for r in missed[:2]]
    if waits:
        you = waits["frees"].get("you")
        if you:
            out.append(L["waits"].format(n=you["needs"], c=you["cards"]))
        quiet = waits["clock"].get("quiet") or []
        if quiet:
            q = quiet[0]
            name = q["card"] if not (private and private.holds(q["card"])) else L["private"]
            out.append(L["build"].format(card=name, d=q["days"]))
    return "\n".join(out)
