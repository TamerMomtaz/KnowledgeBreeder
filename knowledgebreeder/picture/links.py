"""kb opens the links you send it and keeps the words of the page.

A link sent to the inbox (alone, or inside a pasted post) is fetched once, on this laptop, the way a browser reads a
page with scripts off: one GET, no cookies, no login, no script run. kb keeps the page's title and words beside the
link, so Find chances and Your ideas can read them. A PDF link is read like a PDF you attach.

Limits, on purpose:
- only http and https, and only addresses on the internet. An address on this laptop or your home network is never
  opened, so a link can never make kb poke at your router or your other machines;
- up to 5 MB and 20 seconds a page, and up to 3 links in one paste;
- a page that needs a login (LinkedIn, X, Facebook and the like often do) gives only its sign-in wall. kb says so,
  and keeps the link: paste the post's words, or a screenshot, instead.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 20
MAX_LINKS = 3
AGENT = "Mozilla/5.0 (X11; Linux x86_64) kb-link-reader/1 (KnowledgeBreeder, reads one page you sent it)"
URLS = re.compile(r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE)
_BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "section",
          "article", "header", "footer", "blockquote", "pre", "table", "figcaption", "dt", "dd"}
_WALL = re.compile(r"\b(sign in|log in|login|join now|create an account|تسجيل الدخول)\b", re.IGNORECASE)


class LinkError(Exception):
    """Why a link could not be read, as one plain sentence."""


def found(text: str) -> list[str]:
    """The web addresses in a text, in order, each once, without a full stop or comma stuck to the end."""
    out: list[str] = []
    for u in URLS.findall(text or ""):
        u = u.rstrip(".,;:!?،")
        if u not in out:
            out.append(u)
    return out


def _public(host: str) -> None:
    """Refuse an address on this machine or a private network, by every address the name points to."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        raise LinkError(f"{host} could not be found on the internet") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise LinkError(f"{host} is on this laptop or a private network, and kb opens only internet addresses")


class _Checked(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another internet address over http or https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _check(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise LinkError("kb opens only http and https addresses")
    if parts.username or parts.password:
        raise LinkError("the link carries a name or password, so kb does not open it")
    _public(parts.hostname)


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.title: list[str] = []
        self.skip = 0
        self.in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "svg", "nav"):
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            a = {k: (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:title", "og:description", "description") and a.get("content"):
                self.meta.setdefault(key, a["content"])
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg", "nav"):
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self.in_title = False
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.skip:
            self.out.append(data)


def page_text(raw: str) -> tuple[str, str]:
    """(title, words) of an HTML page, without its scripts, styles and menus."""
    p = _Page()
    p.feed(raw)
    title = " ".join("".join(p.title).split()) or p.meta.get("og:title", "")
    lines = [" ".join(ln.split()) for ln in "".join(p.out).splitlines()]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    desc = p.meta.get("og:description") or p.meta.get("description") or ""
    if desc and desc not in body:
        body = (desc + "\n\n" + body).strip()
    return title, body


def fetch(url: str) -> tuple[str, str]:
    """(title, words) of the page at url. Raises LinkError with a plain reason when it cannot be read."""
    _check(url)
    opener = urllib.request.build_opener(_Checked())
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
                                               "Accept-Language": "en,ar;q=0.8"})
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            kind = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read(MAX_BYTES + 1)
            charset = r.headers.get_content_charset() or "utf-8"
    except LinkError:
        raise
    except urllib.error.HTTPError as e:
        raise LinkError(f"the site answered {e.code}" + (", which usually means it wants you signed in"
                                                         if e.code in (401, 403, 999) else "")) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        why = getattr(e, "reason", e)
        if isinstance(why, LinkError):
            raise why from None
        raise LinkError(f"the page did not open ({type(why).__name__})") from None
    if len(data) > MAX_BYTES:
        raise LinkError(f"the page is bigger than {MAX_BYTES // (1024 * 1024)} MB")
    if data.startswith(b"%PDF-") or kind == "application/pdf":
        from .inbox import read
        text, status, why = read("pdf", data)
        if status != "read":
            raise LinkError(f"it is a PDF, and {why or 'it has no text kb can read'}")
        return "", text
    if kind and not (kind.startswith("text/") or "html" in kind or "xml" in kind):
        raise LinkError(f"it is a {kind} file, not a page")
    title, body = page_text(data.decode(charset, "replace"))
    if len(body) < 200 and _WALL.search(body + " " + title):
        raise LinkError("the page shows only a sign-in wall, so kb cannot see the post. Paste its words or a "
                        "screenshot instead")
    if not body.strip():
        raise LinkError("the page has no words kb can read (it may be built by scripts)")
    return title, body


def read_all(text: str, opener=fetch) -> tuple[str, list[str]]:
    """The words of every link in a text, up to MAX_LINKS, as one block to keep, and what could not be read."""
    parts, missed = [], []
    for u in found(text)[:MAX_LINKS]:
        try:
            title, body = opener(u)
        except LinkError as e:
            missed.append(f"{u}: {e}")
            continue
        parts.append(f"--- The page at {u}" + (f", called \"{title}\"" if title else "") + f" ---\n{body.strip()}")
    return "\n\n".join(parts), missed
