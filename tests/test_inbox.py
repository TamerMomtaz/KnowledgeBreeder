"""The inbox: what you send from the phone or the laptop is kept on this machine, read where kb can, never sent on."""

from __future__ import annotations

import base64
import io
import json
import re
import threading
import zipfile
from datetime import date

import pytest
from test_serve import ask

from knowledgebreeder.cli import main
from knowledgebreeder.picture import inbox as inb
from knowledgebreeder.picture import serve

DAY = date(2026, 11, 22)


def docx(*paras: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        body = "".join(f'<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{p}</w:t></w:r><w:r><w:tab/>'
                       f'<w:t>end</w:t></w:r></w:p>' for p in paras)
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')
    return b.getvalue()


def pptx(*slides: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for i, s in enumerate(slides, 1):
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld><a:p><a:r><a:t>{s}</a:t></a:r></a:p></p:sld>")
    return b.getvalue()


def pdf(*pages: str) -> bytes:
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    for p in pages:
        c.drawString(72, 720, p)
        c.showPage()
    c.save()
    return b.getvalue()


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
OGG = b"OggS" + b"\0" * 32                       # a WhatsApp voice note is Ogg Opus
M4A = b"\0\0\0\x20ftypM4A " + b"\0" * 32         # an iPhone voice memo


def test_kb_knows_each_kind_by_its_content_and_reads_what_it_can():
    cases = {
        b"A post: the ministry opens a call for AI pilots": ("text", "read", "ministry opens a call"),
        b"https://example.org/call-for-pilots": ("link", "link", "https://example.org/call-for-pilots"),
        "\ufeffنص عربي من منشور".encode(): ("text", "read", "نص عربي من منشور"),
        docx("Tender &amp; terms", "Due in December"): ("word", "read", "Tender & terms\tend\nDue in December"),
        pptx("One", "Two"): ("slides", "read", "[slide 1]\nOne\n\n[slide 2]\nTwo"),
        pdf("Tender for a data platform", "page two"): ("pdf", "read", "[page 1]\nTender for a data platform"),
        PNG: ("image", "waits_image", ""),
        OGG: ("audio", "waits_speech", ""),
        M4A: ("audio", "waits_speech", ""),
        bytes(range(256)): ("other", "not_read", ""),
        b"%PDF-1.7 broken": ("pdf", "not_read", ""),
    }
    for data, (kind, status, text) in cases.items():
        k, _ = inb.sniff(data)
        got, st, _ = inb.read(k, data)
        assert (k, st) == (kind, status), data[:20]
        assert text in got
    assert inb.sniff(pdf(""))[0] == "pdf" and inb.read("pdf", pdf(""))[1] == "no_text"   # a page with no words on it
    assert inb.sniff(docx())[1] == "docx" and inb.read("word", docx())[1] == "empty"


def test_nothing_is_overwritten_and_a_second_note_goes_beside_the_first(tmp_path):
    box = inb.Inbox(tmp_path / "inbox")
    tender = pdf("Tender for a data platform")                     # reportlab stamps the time, so make it once
    a = box.add(tender, "../../etc/tender\u202e.pdf", "look at the deadline", DAY, "phone")
    assert a["new"] and a["kind"] == "pdf" and a["name"] == "tender.pdf" and a["via"] == "phone"
    assert (tmp_path / "inbox" / a["file"]).read_bytes().startswith(b"%PDF")
    assert a["file"] == f"files/{a['id']}.pdf" and re.fullmatch(r"in_[0-9a-f]{12}", a["id"])
    b = box.add(tender, "copy.pdf", "second look", date(2026, 11, 23), "laptop")
    assert not b["new"] and b["id"] == a["id"] and b["name"] == "tender.pdf"          # the same content, kept once
    assert [n["text"] for n in box.get(a["id"])["notes"]] == ["look at the deadline", "second look"]
    text = box.text(box.get(a["id"]))
    assert text.startswith(f"Inbox item {a['id']}, received 2026-11-22, a pdf called tender.pdf.\nThe note with it:")
    assert (tmp_path / "inbox" / "text" / "2026-11-22" / f"{a['id']}.txt").exists()
    c = box.add(OGG, "voice-note.ogg", None, DAY)
    assert c["status"] == "waits_speech" and c["text_file"] is None
    assert len(box.items()) == 2 and box.counts() == {"read": 1, "waits_speech": 1}
    with pytest.raises(KeyError):
        box.add(b"", "empty.txt")
    with pytest.raises(KeyError):
        box.add(b"x" * (inb.MAX_FILE + 1), "big.bin")
    with pytest.raises(KeyError):
        box.get("../items/x")
    assert not list((tmp_path / "inbox").rglob("*.part"))


def test_kb_inbox_on_the_laptop(tmp_path, capsys):
    folder = tmp_path / "inbox"
    f = tmp_path / "post.txt"
    f.write_text("A call for proposals on AI in schools, closing 2026-12-10.", encoding="utf-8")
    d = tmp_path / "terms.docx"
    d.write_bytes(docx("Eligibility: small firms"))
    assert main(["inbox", "--inbox", str(folder)]) == 0
    assert "is empty" in capsys.readouterr().out
    assert main(["inbox", "add", str(f), str(d), "--note", "for the schools project", "--inbox", str(folder),
                 "--today", "2026-11-22"]) == 0
    out = capsys.readouterr().out
    assert out.count("kept: in_") == 2 and f"kb scout read {folder / 'text'}" in out
    assert main(["inbox", "add", str(f), "--inbox", str(folder)]) == 0
    assert "already here: in_" in capsys.readouterr().out
    assert main(["inbox", "add", "--text", "https://example.org/tender", "--inbox", str(folder)]) == 0
    assert "link" in capsys.readouterr().out
    assert main(["inbox", "--inbox", str(folder), "--json"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert sorted(x["kind"] for x in items) == ["link", "text", "word"]
    word = next(x for x in items if x["kind"] == "word")
    assert main(["inbox", "show", word["id"], "--inbox", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "a word called terms.docx" in out and "Note, 2026-11-22: for the schools project" in out
    assert "Eligibility: small firms" in out
    assert main(["inbox", "add", str(tmp_path / "missing.pdf"), "--inbox", str(folder)]) == 2
    assert main(["inbox", "add", str(tmp_path), "--inbox", str(folder)]) == 2
    assert main(["inbox", "show", "in_000000000000", "--inbox", str(folder)]) == 2
    from knowledgebreeder.scout import sources
    assert len(sources([folder / "text"])) == 3                                      # the scout can read them all


@pytest.fixture()
def phone(tmp_path):
    kb = serve.Kb(tmp_path / "none.db", tmp_path / "w" / "lessons.md", 0, today=DAY)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield kb
    srv.shutdown()
    srv.server_close()


def test_the_phone_page_sends_posts_files_and_voice_notes_to_the_laptop(phone, tmp_path):
    kb = phone
    o = {"Origin": "https://artgate.tail1234.ts.net"}
    code, _, doc = ask(kb, "GET", "/")
    assert code == 200 and 'id="inbox"' in doc and "Your inbox (0)" in doc and 'id="send"' in doc and 'id="rec"' in doc
    assert doc.count("<script") == 2 and not re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", doc)
    assert ask(kb, "GET", "/?lang=ar")[2].count('dir="rtl"') == 1

    code, _, said = ask(kb, "POST", "/api/inbox", {"text": "A post about a tender for AI pilots"}, o)
    assert code == 200 and json.loads(said)["kind"] == "text" and json.loads(said)["new"]
    voice = {"name": "voice-note-2026-11-22-1910.webm", "data": base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\0" * 64).decode(),
             "note": "idea for the town page"}
    code, _, said = ask(kb, "POST", "/api/inbox", voice, o)
    assert code == 200 and json.loads(said)["status"] == "waits_speech"
    assert json.loads(ask(kb, "POST", "/api/inbox", voice, o)[2])["new"] is False     # sent twice, kept once
    shot = {"name": "image.png", "data": base64.b64encode(PNG).decode(), "note": "<script>alert(1)</script>"}
    assert json.loads(ask(kb, "POST", "/api/inbox", shot, o)[2])["status"] == "waits_image"
    word = {"name": "terms.docx", "data": base64.b64encode(docx("Eligibility: small firms")).decode()}
    assert json.loads(ask(kb, "POST", "/api/inbox", word, o)[2])["status"] == "read"

    assert ask(kb, "POST", "/api/inbox", {"data": "not base64!"}, o)[0] == 400
    assert ask(kb, "POST", "/api/inbox", {"text": "   "}, o)[0] == 400
    assert ask(kb, "POST", "/api/inbox", {"text": "x"}, {"X-KB": "0"})[0] == 403
    assert ask(kb, "POST", "/api/inbox", {"text": "x"}, {"Origin": "https://evil.example"})[0] == 403
    assert ask(kb, "POST", "/api/lesson", {"text": "x" * (serve.MAX_BODY + 10)}, o)[0] == 413    # the lesson cap holds
    big = {"name": "big.bin", "data": base64.b64encode(b"x" * (inb.MAX_FILE + 1)).decode()}
    code, _, said = ask(kb, "POST", "/api/inbox", big, o)
    assert code == 400 and "20 MB" in json.loads(said)["error"]

    items = inb.Inbox(tmp_path / "w" / "inbox").items()
    assert len(items) == 4 and {x["via"] for x in items} == {"phone"}
    code, _, doc = ask(kb, "GET", "/?kept=4&again=1")
    assert "Your inbox (4)" in doc and "Kept: 4." in doc and "1 already in your inbox." in doc
    assert "terms.docx" in doc and "waits for the speech reader" in doc and "idea for the town page" in doc
    assert "<script>alert(1)" not in doc and doc.count("<script") == 2
    _, _, ar = ask(kb, "GET", "/?lang=ar")
    assert "صندوقك (4)" in ar and "ينتظر قارئ الكلام" in ar and ar.count('dir="rtl"') == 1
    assert set(serve.LABELS["ar"]) == set(serve.LABELS["en"])
