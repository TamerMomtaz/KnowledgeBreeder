"""The margin cartoons: kb's own cast in the empty side margins of a wide screen, drawn inline, hidden from readers."""

from __future__ import annotations

import re

from test_serve import ask, served  # noqa: F401 - served is a fixture

from knowledgebreeder import margins
from knowledgebreeder.picture import serve


def test_the_cartoons_are_drawn_here_and_kept_out_of_the_way():
    out = margins.html()
    assert out.count('aria-hidden="true"') == 4 and out.count("<svg") == 2      # two columns, each hidden
    assert out.count('id="kbm-dots"') == 1 and out.count('id="kbm-cut"') == 1
    assert out.count('filter="url(#kbm-cut)"') == 6                             # six gags, one figure each
    assert not re.search(r"href|<image|<text|https?:", out)                      # no file, no font, no words
    assert "@media screen and (min-width:1472px)" in margins.CSS and "pointer-events:none" in margins.CSS
    page = margins.inject('<html><head></head><body class="x"><main>hi</main></body></html>')
    assert page.index('<body class="x"><div class="kbm kbm-l"') > page.index('<style id="kb-margins">')


def test_the_first_page_and_the_advice_page_carry_them(served):  # noqa: F811
    kb, run_id, _ = served
    for path in ("/", "/?lang=ar", f"/run/{run_id}"):
        doc = ask(kb, "GET", path)[2]
        assert doc.count('<div class="kbm kbm-') == 2 and 'id="kb-margins"' in doc
    first = ask(kb, "GET", "/")[2]
    assert first.count("<script") == 2                                       # no new script came with them
    assert serve.index(None, []).count('<div class="kbm kbm-') == 2
