"""The explainer: a ? on every box that says what the box is and what each of its buttons does, in both languages."""

from __future__ import annotations

import html
import re
import threading

from test_serve import ask, served  # noqa: F401 - served is a fixture
from test_soon import CARDS, TODAY

from knowledgebreeder import explain
from knowledgebreeder.picture import Picture, cards, serve

_SECTION = re.compile(r'<section class="box[^"]*" id="([a-z]+)".*?</section>', re.DOTALL)


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).split())


def _boxes(doc: str) -> dict[str, str]:
    return {m[1]: m[0] for m in _SECTION.finditer(doc)}


def _page(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    pic = Picture()
    pic.add(cards.parse(CARDS), recorded="2026-11-24")
    pic.save(w / "picture.json")
    kb = serve.Kb(w / "runs.db", w / "lessons.md", 0, today=TODAY)
    kb.nudge_post = lambda *a: None
    return kb


def test_every_box_and_every_button_on_the_first_page_is_explained(tmp_path):
    kb = _page(tmp_path)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for lang in ("en", "ar"):
            for on in ("off", "on"):
                ask(kb, "POST", "/api/nudge", {"do": on})
                doc = ask(kb, "GET", f"/?lang={lang}")[2]
                boxes = _boxes(doc)
                assert set(explain.TEXT[lang]["boxes"]) == set(boxes)
                for key, box in boxes.items():
                    assert '<details class="explain">' in box, f"no ? on {key}"
                    head = box.split("</h2>", 1)[1]
                    assert head.startswith('<details class="explain">'), f"the heading of {key} is no longer first"
                    bubble = box.split('<div class="ex-body">', 1)[1].split("</details>", 1)[0]
                    told = {_text(x) for x in re.findall(r"<dt>(.*?)</dt>", bubble)}
                    rest = box.replace(bubble, "")
                    pressed = {_text(x) for x in re.findall(r"<button[^>]*>(.*?)</button>", rest)}
                    linked = {re.sub(r"\s*\(.*$", "", _text(x)) for x in re.findall(r"<a href=\"/[^\"]*\"[^>]*>(.*?)</a>", rest)}
                    assert pressed <= told, f"{lang} {key}: buttons with no words: {pressed - told}"
                    assert linked <= told, f"{lang} {key}: links with no words: {linked - told}"
        assert {"soon", "inbox", "waits", "where", "ask", "nudge", "runs", "lessons"} <= set(boxes)
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_first_page_opens_with_how_to_use_kb_and_can_read_aloud(tmp_path):
    kb = _page(tmp_path)
    srv = serve.make(kb)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        doc = ask(kb, "GET", "/")[2]
        head = doc.split("<header>", 1)[1].split("</header>", 1)[0]
        assert '<details class="explain guide" id="how">' in head and "How to use kb" in head
        assert head.count("<li>") == len(explain.TEXT["en"]["steps"])
        assert doc.count('class="speak"') == len(_boxes(doc)) + 1
        assert 'aria-label="What is Coming up?"' in doc and 'aria-label="What is Your lessons?"' in doc
        assert "<dt><bdi>See chances</bdi></dt>" in doc                 # the count in brackets is left out
        assert doc.count("<script") == 2 and "speechSynthesis" in doc and 'id="kb-explain"' in doc
        ar = ask(kb, "GET", "/?lang=ar")[2]
        assert "كيف تستخدم kb" in ar and 'aria-label="ما هو «قريبًا»؟"' in ar and "<dt><bdi>اطلب نصيحة</bdi></dt>" in ar
        assert "اقرأ بصوت عالٍ" in ar and "fetch(" not in explain.JS      # the reader sends nothing anywhere
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_advice_page_says_how_it_works(served):  # noqa: F811
    kb, run_id, _ = served
    doc = ask(kb, "GET", f"/run/{run_id}")[2]
    assert "How this page works" in doc and doc.count("<li>Press Save.") == 1 and 'id="kb-explain"' in doc
    assert "كيف تعمل هذه الصفحة" in ask(kb, "GET", f"/run/{run_id}?lang=ar")[2]
    from knowledgebreeder.picture import page
    from knowledgebreeder.runlog import RunLog
    log = RunLog(kb.runlog)
    try:
        static = page.build(page.gather(log, run_id), page.history(log))
    finally:
        log.close()
    assert "How this page works" not in static and "speechSynthesis" not in static    # the file you keep stays as it was
