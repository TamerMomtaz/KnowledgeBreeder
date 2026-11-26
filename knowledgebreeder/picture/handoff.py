"""kb hands its build list to Claude on GitHub, so pressing a button starts the build.

The page's "Send to Claude" opens one GitHub issue in kb's own repository with the lines on the build list and a
request to @claude. The repository's Claude workflow (.github/workflows/claude.yml) answers it: Claude builds the
lines on a branch and opens a pull request. Nothing reaches kb until you merge that pull request.

What leaves this laptop, and what does not:
- kb's repository is public, so the issue is public. A line that names anything on your private list, a card marked
  #private, a phone, an email, a key or money stays here: kb leaves it out of the issue and says how many it held.
- The card a line came from is named only when the card itself may leave the laptop.
- kb needs a GitHub key for this, kept like the model keys: kb keys add github. The key only opens issues; it
  never leaves the laptop except to GitHub, and kb never prints it.
- A line is sent once. kb remembers the issue for each line in work/handoff.json, so a second press sends only
  what was added since.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from . import private as prv

KEY = "KB_GITHUB_TOKEN"
REPO = "TamerMomtaz/KnowledgeBreeder"
API = "https://api.github.com"
KEY_PAGE = "https://github.com/settings/personal-access-tokens/new"
ASK = ("@claude please build the lines below into KnowledgeBreeder (kb), on a new branch, and open a pull request.\n"
       "- Read README.md first and keep kb's ways: plain words on the page, English and Arabic labels, an explainer "
       "line for every new button, and tests for everything new.\n"
       "- Run the tests (pytest) and keep them green.\n"
       "- If a line is too big for one pull request, build its first useful step and say on this issue what is left.\n"
       "- If a line is unclear, ask here instead of guessing.\n"
       "- Never commit the owner's private files: picture.json, cards, journey files, work/, keys.")


class HandoffError(Exception):
    """Why the build list could not be handed to Claude, as one plain sentence."""


def repo() -> str:
    return os.environ.get("KB_GITHUB_REPO") or REPO


class Sent:
    """Which build-list lines went to Claude, and in which issue."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def all(self) -> dict[str, dict]:
        try:
            got = json.loads(self.path.read_text(encoding="utf-8")).get("sent") or {}
        except (OSError, ValueError, AttributeError):
            return {}
        return {k: v for k, v in got.items() if isinstance(v, dict) and v.get("url")}

    def add(self, ids: list[str], number: int, url: str, today: date) -> None:
        sent = self.all()
        for i in ids:
            sent[i] = {"issue": number, "url": url, "at": today.isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".part")
        tmp.write_text(json.dumps({"sent": sent}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


def split(items: list[dict], guard: prv.Private, cards_out: set[str]) -> tuple[list[dict], int]:
    """(the lines that may go into a public issue, how many stay on this laptop). A card's name goes along only when
    the card may leave: cards_out names those."""
    keep, held = [], 0
    for x in items:
        text = f"{x['what']} {x.get('why') or ''}"
        if guard.holds(text):
            held += 1
            continue
        keep.append({**x, "card": x["card"] if x["card"] in cards_out else "one of my cards"})
    return keep, held


def title(items: list[dict]) -> str:
    first = " ".join(items[0]["what"].split())
    first = first if len(first) <= 70 else first[:69].rstrip() + "…"
    more = len(items) - 1
    return f"kb build: {first}" + (f" (and {more} more)" if more else "")


def body(items: list[dict], held: int) -> str:
    rows = [ASK, "", "The build list (from the owner's project cards):"]
    for i, x in enumerate(items, 1):
        why = f": {x['why']}" if x.get("why") else ""
        rows.append(f"{i}. {x['what']} (from {x['card']}{why})")
    if held:
        rows += ["", f"{held} more line(s) stayed on the owner's laptop because they name something private."]
    rows += ["", "Sent from kb's page, Send to Claude."]
    return "\n".join(rows)


def _post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "kb-handoff/1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        why = {401: "GitHub did not accept the key. Make a new one and keep it with: kb keys add github",
               403: "the GitHub key may not open issues here. Give it Issues: Read and write on KnowledgeBreeder",
               404: "GitHub cannot find the repository for this key. Give the key access to KnowledgeBreeder",
               410: "issues are turned off on the repository. Turn them on in its Settings",
               422: "GitHub refused the issue as written"}.get(e.code, f"GitHub answered {e.code}")
        raise HandoffError(why) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HandoffError(f"GitHub could not be reached ({type(getattr(e, 'reason', e)).__name__})") from None


def send(items: list[dict], guard: prv.Private, cards_out: set[str], sent: Sent, today: date,
         token: str | None = None, post=_post) -> dict:
    """Open one issue with the build-list lines not sent before. Returns {number, url, sent, held, already}."""
    before = sent.all()
    fresh = [x for x in items if x["id"] not in before]
    if not items:
        raise HandoffError("the build list is empty. Press Build this on a line first")
    if not fresh:
        return {"number": None, "url": next(iter(before.values()))["url"] if before else "", "sent": 0, "held": 0,
                "already": len(items)}
    keep, held = split(fresh, guard, cards_out)
    if not keep:                                    # only private lines are new: nothing may go
        return {"number": None, "url": "", "sent": 0, "held": held, "already": len(items) - len(fresh)}
    token = token or os.environ.get(KEY)
    if not token:
        raise HandoffError("kb has no GitHub key yet. In a terminal type: kb keys add github")
    got = post(f"{API}/repos/{repo()}/issues", token, {"title": title(keep), "body": body(keep, held)})
    number, url = got.get("number"), got.get("html_url")
    if not number or not url:
        raise HandoffError("GitHub answered without an issue")
    sent.add([x["id"] for x in keep], int(number), str(url), today)
    return {"number": int(number), "url": url, "sent": len(keep), "held": held, "already": len(items) - len(fresh)}
