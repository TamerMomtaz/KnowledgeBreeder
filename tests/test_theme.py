"""kb's look and its game layer: the record counts only what you rated, and every page wears the same look.

The rows are invented. A review is one model's answer you rated, five make a level, a streak is days in a row with a
rated run, and a model's rank is how often you would act on its advice.
"""

from __future__ import annotations

import re
from datetime import date

from knowledgebreeder import theme


def _row(day, **would_act):
    return {"run": f"run_{day}", "date": day,
            "workers": {w: {"would_act": v, "picked": None} for w, v in would_act.items()}}


HIST = [_row("2026-11-22", small=1.0, big=None), _row("2026-11-21", small=0.5, big=0.0),
        _row("2026-11-20", small=0.75, big=1 / 3), _row("2026-11-18", small=1.0, big=0.0)]


def test_the_record_counts_only_what_you_rated():
    st = theme.standing(HIST, date(2026, 11, 22))
    assert st["reviews"] == 7 and st["level"] == 2 and st["into"] == 2      # big's open answer is not a review
    assert st["streak"] == 3                                                # 18 is not joined to 20
    assert st["models"]["small"]["rank"] == "S" and st["models"]["small"]["runs"] == 4
    assert st["models"]["big"]["rank"] == "D" and st["models"]["big"]["runs"] == 3
    assert theme.standing(HIST, date(2026, 11, 23))["streak"] == 3          # rated yesterday still counts
    assert theme.standing(HIST, date(2026, 11, 24))["streak"] == 0
    empty = theme.standing([], date(2026, 11, 22))
    assert empty == {"reviews": 0, "level": 1, "into": 0, "streak": 0, "models": {}}
    assert [theme.rank(x) for x in (0.7, 0.69, 0.5, 0.35, 0.2, 0.19, None)] == ["S", "A", "A", "B", "C", "D", ""]


def test_the_status_window_and_the_seals_say_it_in_words():
    st = theme.standing(HIST, date(2026, 11, 22))
    h = theme.hud(st)
    assert 'aria-valuenow="2"' in h and h.count('<i class="f">') == 2 and "3 more to level 3." in h
    assert "7 reviews so far." in h and '<span class="streak">3-day streak.</span>' in h
    first = theme.hud(theme.standing([], date(2026, 11, 22)))
    assert "A review is one model&#x27;s answer you rated." in first and "Rate a run today to start a streak." in first
    s = theme.seal("small", st)
    assert 'role="img"' in s and "you would act on 81% of its advice, over 4 rated runs" in s and ">S</span>" in s
    assert "Not ranked yet" in theme.seal("nobody", st) and theme.seal("small", None) == ""
    ar = theme.hud(st, "ar")
    assert "المستوى" in ar and "أيام متتالية" in ar


def test_every_page_wears_one_look_and_fetches_nothing():
    page = "<html><head><style>body{}</style></head><body><p>x</p></body></html>"
    once = theme.inject(page)
    assert once.count('<style id="kb-look">') == 1 and once.index('id="kb-look"') > once.index("body{}")
    assert not re.search(r"url\(|@import|@font-face|https?://", theme.CSS)  # the page may load nothing
    assert "prefers-reduced-motion: no-preference" in theme.CSS             # it moves only if you allow motion
    assert "prefers-color-scheme: dark" in theme.CSS


def test_the_town_and_the_plant_walk_wear_it_too():
    from pathlib import Path

    from knowledgebreeder.graph import PlantGraph
    from knowledgebreeder.picture import Picture, cards, town
    from knowledgebreeder.walk import build

    here = Path(__file__).parent / "fixtures"
    pic = Picture()
    pic.add(cards.parse((here / "demo_cards.md").read_text(encoding="utf-8")))
    for doc in (town.build(pic, today=date(2026, 11, 22)), build(PlantGraph.load(here / "demo_graph.json"))):
        assert doc.count('<style id="kb-look">') == 1 and doc.count("<script") == 2
