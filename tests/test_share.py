"""Share to kb: the phone's Share menu lists kb once kb is on its home screen. These check what the laptop serves for
that (the manifest, the share helper and the icons) and that a share the helper did not catch changes nothing."""

from __future__ import annotations

import json
import struct
import threading
import zlib
from datetime import date

import pytest
from test_serve import ask

from knowledgebreeder.picture import icon, serve


@pytest.fixture()
def kb(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    k = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=date(2026, 11, 24))
    srv = serve.make(k)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield k
    srv.shutdown()
    srv.server_close()


def test_the_page_names_its_manifest_and_the_manifest_offers_a_share_target(kb):
    code, head, doc = ask(kb, "GET", "/")
    assert code == 200 and '<link rel="manifest" href="/manifest.webmanifest">' in doc and doc.count("<script") == 2
    csp = head["Content-Security-Policy"]
    assert "manifest-src 'self'" in csp and "worker-src 'self'" in csp and "default-src 'none'" in csp
    code, head, body = ask(kb, "GET", "/manifest.webmanifest")
    m = json.loads(body)
    assert code == 200 and head["Content-Type"].startswith("application/manifest+json")
    assert m["start_url"] == "/" and m["display"] == "standalone" and {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"}
    st = m["share_target"]
    assert st["action"] == "/share" and st["method"] == "POST" and st["enctype"] == "multipart/form-data"
    assert st["params"]["files"][0]["name"] == "files" and "image/*" in st["params"]["files"][0]["accept"]
    code, head, js = ask(kb, "GET", "/sw.js")
    assert code == 200 and head["Content-Type"].startswith("text/javascript") and '"/share"' in js and "kb-share" in js


@pytest.mark.parametrize("size", [192, 512])
def test_the_icons_are_real_pngs_of_the_right_size(kb, size):
    c = __import__("http.client").client.HTTPConnection("127.0.0.1", kb.port, timeout=10)
    c.request("GET", f"/icon-{size}.png", headers={"Host": f"127.0.0.1:{kb.port}"})
    r = c.getresponse()
    data = r.read()
    c.close()
    assert r.status == 200 and r.getheader("Content-Type") == "image/png" and data == icon.png(size)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (size, size)
    raw = zlib.decompress(data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8])
    assert len(raw) == size * (1 + 3 * size)
    middle = raw[(size // 2) * (1 + 3 * size) + 1 + 3 * (size // 2):][:3]
    assert tuple(middle) == icon.PLATE                    # the plate sits in the middle, inside a round mask


def test_a_share_the_helper_did_not_catch_keeps_nothing_and_asks_to_share_again(kb):
    c = __import__("http.client").client.HTTPConnection("127.0.0.1", kb.port, timeout=10)
    body = (b"--x\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\nhello from another site\r\n--x--\r\n")
    c.request("POST", "/share", body=body, headers={"Host": f"127.0.0.1:{kb.port}", "Origin": "https://evil.example",
                                                    "Content-Type": "multipart/form-data; boundary=x"})
    r = c.getresponse()
    r.read()
    c.close()
    assert r.status == 303 and r.getheader("Location") == "/?shared=again#inbox"
    assert kb.inbox.items() == []
    code, _, doc = ask(kb, "GET", "/?shared=again")
    assert code == 200 and "share_again" in doc                 # the page has the sentence ready for its script
    assert ask(kb, "POST", "/share", headers={"Host": "evil.example"}, host="evil.example")[0] == 421


@pytest.mark.parametrize("name", ["INDEX_JS", "WHERE_JS", "SW_JS"])
def test_the_page_scripts_parse(name, tmp_path):
    node = __import__("shutil").which("node")
    if not node:
        pytest.skip("node is not installed here")
    f = tmp_path / f"{name}.js"
    f.write_text(getattr(serve, name), encoding="utf-8")
    r = __import__("subprocess").run([node, "--check", str(f)], capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr
