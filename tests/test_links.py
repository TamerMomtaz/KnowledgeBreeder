"""kb opens the links you send: the page's words are kept beside the link, and only internet addresses are opened."""

from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from knowledgebreeder.models import config
from knowledgebreeder.picture import inbox as inb
from knowledgebreeder.picture import links

TODAY = date(2026, 11, 26)
PAGE = """<html><head><title>Saturday baking class</title><meta property="og:description" content="Bread for beginners.">
<script>alert(1)</script><style>p{}</style></head><body><nav>Home | About</nav>
<article><h1>Bread</h1><p>Knead for ten minutes.</p><p>Let it rise overnight.</p></article></body></html>"""


def stand_in(pages: dict[str, tuple[str, str]]):
    def opener(url):
        if url not in pages:
            raise links.LinkError("the site answered 403, which usually means it wants you signed in")
        return pages[url]
    return opener


def test_found_takes_each_address_once_without_the_full_stop_after_it():
    t = "Look at https://example.org/a. And https://example.org/b, then https://example.org/a again"
    assert links.found(t) == ["https://example.org/a", "https://example.org/b"]
    assert links.found("no links here") == []


def test_a_page_keeps_its_title_and_words_without_scripts_styles_or_menus():
    title, body = links.page_text(PAGE)
    assert title == "Saturday baking class"
    assert body.startswith("Bread for beginners.") and "Knead for ten minutes." in body
    assert "alert" not in body and "Home | About" not in body and "p{}" not in body


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/", "http://localhost/", "http://192.168.1.1/admin",
                                 "http://10.0.0.5/", "file:///etc/passwd", "ftp://example.org/x",
                                 "https://me:secret@example.org/"])
def test_only_internet_addresses_over_http_are_opened(url):
    with pytest.raises(links.LinkError):
        links.fetch(url)


def test_a_link_sent_alone_is_opened_and_its_words_kept_beside_it(tmp_path):
    box = inb.Inbox(tmp_path, opener=stand_in({"https://example.org/bread": ("Bread", "Knead for ten minutes.")}))
    item = box.add_text("https://example.org/bread", today=TODAY)
    assert item["kind"] == "link" and item["status"] == "read" and item["links"] == {"read": 1, "missed": []}
    kept = box.text(item)
    assert "https://example.org/bread" in kept and 'The page at https://example.org/bread, called "Bread"' in kept
    assert "Knead for ten minutes." in kept
    assert inb.say(item) == f"read: {item['chars']:,} characters, with 1 page(s) its links open to"
    assert (tmp_path / item["file"]).read_text() == "https://example.org/bread"       # the link as it came, untouched


def test_a_post_with_links_keeps_its_words_and_says_why_a_link_did_not_open(tmp_path):
    box = inb.Inbox(tmp_path, opener=stand_in({"https://example.org/bread": ("", "Let it rise overnight.")}))
    item = box.add_text("Two classes: https://example.org/bread and https://www.linkedin.com/posts/x", today=TODAY)
    assert item["status"] == "read" and item["links"]["read"] == 1
    assert "Let it rise overnight." in box.text(item)
    assert item["links"]["missed"][0].startswith("https://www.linkedin.com/posts/x: the site answered 403")
    alone = box.add_text("https://www.linkedin.com/posts/x", today=TODAY)
    assert alone["status"] == "link"
    assert inb.say(alone) == ("a link: kept, but kb could not open it. Why: the site answered 403, which usually "
                              "means it wants you signed in.")
    assert "رابط" in inb.say(alone, "ar")


def test_without_an_opener_a_link_is_kept_as_text_and_the_old_ones_are_opened_once_later(tmp_path):
    item = inb.Inbox(tmp_path).add_text("https://example.org/bread", today=TODAY)
    assert item["status"] == "link" and "links" not in item and item["text_file"]
    box = inb.Inbox(tmp_path, opener=stand_in({"https://example.org/bread": ("Bread", "Knead for ten minutes.")}))
    done = box.open_links()
    assert [x["id"] for x in done] == [item["id"]]
    again = box.get(item["id"])
    assert again["status"] == "read" and "Knead for ten minutes." in box.text(again)
    assert box.open_links() == []                                                       # each item is tried once


def test_fetch_reads_a_page_and_says_when_it_shows_only_a_sign_in_wall(monkeypatch):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (PAGE if self.path == "/page" else "<html><title>Sign in</title><p>Sign in to see this post</p>"
                    ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(links, "_public", lambda host: None)                # this one test server is on the laptop
    monkeypatch.setattr(links.urllib.request, "getproxies", dict, raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    try:
        base = f"http://127.0.0.1:{srv.server_port}"
        title, body = links.fetch(base + "/page")
        assert title == "Saturday baking class" and "Let it rise overnight." in body
        with pytest.raises(links.LinkError, match="sign-in wall"):
            links.fetch(base + "/wall")
    finally:
        srv.shutdown()
        srv.server_close()


def test_kb_keys_add_kimi_gives_an_older_kimi_entry_its_price(tmp_path):
    f = tmp_path / "models.json"
    entry = dict(config.PRESETS["kimi"]["entry"])
    entry.pop("price_in"), entry.pop("price_out")
    f.write_text(json.dumps({"default": "kimi", "models": {"kimi": entry}}))
    assert config.fill_price(f, "kimi") is True
    got = json.loads(f.read_text())["models"]["kimi"]
    assert (got["price_in"], got["price_out"]) == (4.0, 20.0)
    assert config.fill_price(f, "kimi") is False                                        # once is enough
    assert config.fill_price(f, "gemini") is False                                      # no price known, nothing made up
