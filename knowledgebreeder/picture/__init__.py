"""The whole picture: one person's projects as one graph, read from cards.

A *card* is what one project says about itself under fixed headings: what
exists, what it can do, what it needs, what is unfinished, what could travel,
what it links to. Cards come from anywhere (a repo read, a chat, a notebook)
as plain text. The picture merges them and reads them four ways:

    overlaps   the same idea in more than one project
    gaps       needs not met, work not finished, decisions waiting, things named but never described
    reuse      a part in one project that could serve another
    brief      a short list of moves worth a look, each with its source

and draws them as a town: areas are districts, projects are buildings, in one
HTML file that opens with no internet.

A picture is private. It lives in one local file (work/picture.json by default,
which git ignores) and nothing here sends it anywhere.

    from knowledgebreeder.picture import Picture, cards, reports
    pic = Picture()
    pic.add(cards.parse_file("my-cards.md"))
    print(reports.brief_md(reports.brief(pic)))
"""

from . import cards, reports
from .store import Picture

__all__ = ["Picture", "cards", "reports"]
