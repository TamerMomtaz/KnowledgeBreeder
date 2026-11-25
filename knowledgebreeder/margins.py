"""Margin cartoons: kb's own little cast, drawn in ink in the empty side margins of a wide screen.

In the spirit of the small wordless gags that run down the margins of a humour magazine, but with a cast of kb's own:
Sprout, a small figure with a seedling on its head, doing kb's jobs. On the left, work coming in: it runs in with a
letter, waters a stack of cards until something grows, and dozes on a quiet stack while the clock rings. On the
right, what kb gives back: it shouts a reminder into a phone, stamps your decision with the red seal, and climbs the
level ladder to a gold star.

They are inline SVG, drawn here with no file and no font, coloured by the theme (ink, the red seal, gold), and hidden
from screen readers. They show only when the screen is wide enough to leave room beside the page, and never in print.
"""

from __future__ import annotations

WIDTH = 1240                     # the page's own width; the cartoons live outside it


def _n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _p(*pts: tuple[float, float]) -> str:
    return "M" + " L".join(f"{_n(x)} {_n(y)}" for x, y in pts)


def _limb(pts, w: float, cls: str = "l") -> str:
    return f'<path class="{cls}" stroke-width="{_n(w)}" d="{_p(*pts)}"/>'


def sprout(x: float, y: float, s: float = 1.25, lean: float = 0, arms=None, legs=None, flip: bool = False,
           head: tuple[float, float] = (0, 0), hip: tuple[float, float] = (0, -24), extra: str = "") -> str:
    """Sprout, standing on (x, y). Local units: the feet near 0, the top of the leaf near -78. ``arms`` and ``legs``
    are ((elbow or knee), (hand or foot)) pairs; ``flip`` faces it left."""
    sh = (hip[0] + lean, hip[1] - 16)
    hd = (sh[0] + lean * 0.35 + head[0], sh[1] - 13 + head[1])
    arms = arms or (((sh[0] - 7, sh[1] + 9), (sh[0] - 9, sh[1] + 20)), ((sh[0] + 7, sh[1] + 9), (sh[0] + 9, sh[1] + 20)))
    legs = legs or (((hip[0] - 4, hip[1] + 12), (hip[0] - 6, 0)), ((hip[0] + 4, hip[1] + 12), (hip[0] + 6, 0)))
    out = [_limb([hip, sh], 15)]
    for (kx, ky), (fx, fy) in legs:
        out.append(_limb([(hip[0], hip[1] + 2), (kx, ky), (fx, fy - 2)], 7.5))
        out.append(f'<ellipse cx="{_n(fx + 2.5)}" cy="{_n(fy - 2)}" rx="5.5" ry="3.4"/>')
    for i, ((ex, ey), (hx, hy)) in enumerate(arms):
        out.append(_limb([(sh[0] + (2 if i else -2), sh[1] + 2), (ex, ey), (hx, hy)], 6))
        out.append(f'<circle cx="{_n(hx)}" cy="{_n(hy)}" r="3.6"/>')
    out.append(f'<circle cx="{_n(hd[0])}" cy="{_n(hd[1])}" r="11.5"/>')
    tx, ty = hd[0] + 1.5, hd[1] - 22                       # the seedling: a stem and two leaves
    out.append(f'<path class="l" stroke-width="2.6" d="M{_n(hd[0])} {_n(hd[1] - 10)} Q{_n(hd[0] - 1.5)} '
               f'{_n(hd[1] - 17)} {_n(tx)} {_n(ty)}"/>')
    out.append(f'<path d="M{_n(tx)} {_n(ty)} C{_n(tx + 4)} {_n(ty - 7)} {_n(tx + 12)} {_n(ty - 8)} {_n(tx + 16)} '
               f'{_n(ty - 4)} C{_n(tx + 12)} {_n(ty + 1)} {_n(tx + 4)} {_n(ty + 1.5)} {_n(tx)} {_n(ty)}Z"/>')
    out.append(f'<path d="M{_n(tx)} {_n(ty)} C{_n(tx - 3)} {_n(ty - 6)} {_n(tx - 9)} {_n(ty - 6)} {_n(tx - 12)} '
               f'{_n(ty - 3)} C{_n(tx - 9)} {_n(ty + 1)} {_n(tx - 3)} {_n(ty + 1)} {_n(tx)} {_n(ty)}Z"/>')
    sx = -s if flip else s
    return (f'<g filter="url(#kbm-cut)"><g transform="translate({_n(x)} {_n(y)}) scale({_n(sx)} {_n(s)})">'
            f'{"".join(out)}{extra}</g></g>')


def _tone(cx: float, cy: float, r: float) -> str:
    """The screentone disc a figure stands in front of."""
    return f'<circle class="t" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="url(#kbm-dots)"/>'


def _speed(x: float, y: float, lengths, gap: float = 9, w: float = 2.2) -> str:
    return "".join(_limb([(x - ln, y + i * gap), (x, y + i * gap)], w, "l s") for i, ln in enumerate(lengths))


def _ground(x1: float, x2: float, y: float) -> str:
    return _limb([(x1, y), (x2, y)], 2.4, "l s")


# ---- the six gags ----------------------------------------------------------------------------------------------------
def courier() -> str:
    """Running in with a letter: your inbox."""
    letter = ('<g transform="translate(27 -50) rotate(-10)"><rect x="0" y="0" width="30" height="20" rx="2"/>'
              '<path class="c" stroke-width="2" d="M1.5 1.5 L15 11 L28.5 1.5"/><circle class="r" cx="15" cy="11" r="4"/></g>')
    fig = sprout(70, 170, lean=7,
                 arms=(((4, -33), (-8, -38)), ((19, -40), (29, -43))),
                 legs=(((-5, -11), (-18, -15)), ((12, -15), (13, 0))), extra=letter)
    puffs = '<circle cx="34" cy="166" r="5"/><circle cx="24" cy="160" r="3.6"/><circle cx="16" cy="165" r="2.6"/>'
    return _tone(84, 104, 60) + _speed(44, 92, (30, 22, 34, 18), 10) + fig + puffs + _ground(14, 150, 172)


def gardener() -> str:
    """Watering a stack of cards until something grows: your picture."""
    can = ('<rect x="17" y="-47" width="19" height="15" rx="3"/><path class="l" stroke-width="2.6" d="M20 -47 Q26.5 -57 33 -47"/>'
           '<path class="l" stroke-width="3.4" d="M35 -42 L50 -52"/>')
    fig = sprout(38, 172, lean=3, arms=(((12, -34), (19, -40)), ((14, -40), (21, -45))), extra=can)
    drops = "".join(f'<path class="s" d="M{x} {y} q2.6 4.2 0 6.4 q-2.6 -2.2 0 -6.4Z"/>'
                    for x, y in ((104, 112), (109, 122), (101, 129)))
    cards = ('<g transform="translate(96 146) rotate(-6)"><rect x="0" y="0" width="46" height="9" rx="2"/>'
             '<rect x="3" y="10" width="46" height="9" rx="2"/><rect x="-1" y="20" width="46" height="9" rx="2"/></g>')
    plant = ('<path class="l" stroke-width="3.4" d="M120 144 C118 132 123 124 121 112"/>'
             '<path class="g" d="M121 120 C128 108 142 106 149 112 C141 122 130 124 121 120Z"/>'
             '<path class="g" d="M120 128 C113 118 101 117 95 122 C102 131 112 132 120 128Z"/>'
             '<path class="g" d="M121 112 C119 103 123 96 128 93 C130 101 127 108 121 112Z"/>')
    return _tone(82, 108, 58) + cards + plant + drops + fig + _ground(10, 152, 174)


def dozer() -> str:
    """Asleep on a quiet stack while the clock rings: the cards that went quiet, and what is coming up."""
    stack = ('<rect x="64" y="128" width="62" height="12" rx="2"/><rect x="60" y="141" width="62" height="12" rx="2"/>'
             '<rect x="66" y="154" width="62" height="12" rx="2"/>')
    fig = sprout(110, 157, lean=6, head=(6, 9),
                 arms=(((9, -28), (13, -21)), ((12, -30), (17, -22))),
                 legs=(((13, -23), (15, -3)), ((10, -22), (19, -4))))
    zz = ('<path class="l" stroke-width="2.6" d="M96 70 L106 70 L96 80 L106 80"/>'
          '<path class="l" stroke-width="2.2" d="M84 54 L91 54 L84 61 L91 61"/>')
    clock = ('<g transform="translate(34 154)"><circle class="r" cx="0" cy="0" r="11"/><circle class="r" cx="-9" cy="-10" r="4.4"/>'
             '<circle class="r" cx="9" cy="-10" r="4.4"/><path class="c" stroke-width="2" d="M0 -6 L0 0 L5 3"/>'
             '<path class="l" stroke-width="3" d="M-7 9 L-10 14 M7 9 L10 14"/></g>')
    shake = ('<path class="l s" stroke-width="2.2" d="M14 140 L19 144 M12 152 L18 152 M14 164 L19 160 M54 140 L49 144 '
             'M56 152 L50 152"/>')
    return _tone(90, 100, 58) + stack + fig + zz + clock + shake + _ground(10, 152, 168)


def caller() -> str:
    """Shouting a reminder into the phone: the nudges."""
    phone = ('<g transform="translate(22 92) rotate(-8)"><rect x="0" y="0" width="34" height="62" rx="6"/>'
             '<rect class="c" x="4" y="7" width="26" height="44" rx="2" stroke-width="2"/>'
             '<circle class="r" cx="31" cy="2" r="7"/></g>')
    buzz = ('<path class="l s" stroke-width="2.2" d="M12 96 L6 92 M10 112 L3 112 M12 128 L6 132 M66 86 L71 80 '
            'M70 100 L77 98"/>')
    horn = '<path d="M-14 -50 L-34 -60 L-34 -34 L-14 -42Z"/><rect x="-16" y="-50" width="6" height="9" rx="1.5"/>'
    fig = sprout(112, 170, lean=-4, arms=(((-16, -38), (-12, -46)), ((-6, -30), (-12, -43))),
                 legs=(((-6, -12), (-9, 0)), ((5, -12), (8, 0))), extra=horn)
    blast = ('<path class="l s" stroke-width="2.2" d="M70 104 L62 98 M70 114 L60 114 M70 124 L62 130"/>')
    return _tone(80, 108, 58) + phone + buzz + blast + fig + _ground(10, 152, 172)


def stamper() -> str:
    """Bringing the red seal down on a decision."""
    stamp = ('<g transform="translate(0 -96)"><rect x="-4" y="-16" width="8" height="18" rx="3"/>'
             '<circle cx="0" cy="-19" r="7"/><rect class="r" x="-17" y="2" width="34" height="13" rx="2"/></g>')
    fig = sprout(70, 166, lean=0, arms=(((-19, -57), (-12, -80)), ((19, -57), (12, -80))),
                 legs=(((-9, -12), (-12, 0)), ((9, -12), (12, 0))), extra=stamp)
    paper = ('<g transform="translate(92 150) rotate(4)"><rect x="0" y="0" width="54" height="18" rx="1.5"/>'
             '<circle class="rr" cx="27" cy="9" r="7" stroke-width="2.4"/>'
             '<path class="rr" stroke-width="2.6" d="M23.5 9 L26.5 12 L31 5.5"/></g>')
    hits = '<path class="l s" stroke-width="2.2" d="M100 132 L96 124 M118 128 L118 118 M136 132 L140 124"/>'
    return _tone(78, 100, 58) + fig + paper + hits + _ground(10, 152, 168)


def climber() -> str:
    """Climbing the level ladder to a gold star."""
    steps = "".join(f'<path d="M{_n(x)} {_n(y)} l24 0 l-4 8 l-24 0Z"/>'
                    for x, y in ((24, 160), (46, 140), (68, 120), (90, 100), (112, 80)))
    fig = sprout(56, 140, s=1.15, lean=5, arms=(((-5, -31), (-12, -24)), ((15, -50), (24, -63))),
                 legs=(((-3, -12), (-3, 0)), ((11, -28), (21, -17))))
    star = ('<path class="g" d="M134 34 l5 10.5 l11.5 1.6 l-8.4 8 l2.1 11.4 l-10.2 -5.5 l-10.2 5.5 l2.1 -11.4 '
            'l-8.4 -8 l11.5 -1.6Z"/>'
            '<path class="l s" stroke-width="2.2" d="M134 22 L134 16 M150 32 L156 27 M118 32 L112 27 M154 50 L160 52"/>')
    return _tone(88, 96, 58) + steps + fig + star


CELL = 200                       # each gag's height in the column


def column(gags, dots: bool = False) -> str:
    cells = "".join(f'<g transform="translate(0 {i * CELL})">{g()}</g>' for i, g in enumerate(gags))
    defs = ('<defs><pattern id="kbm-dots" width="6" height="6" patternUnits="userSpaceOnUse">'
            '<circle cx="3" cy="3" r="1.15" fill="currentColor"/></pattern>'
            # a thin cut of paper colour round each figure, so an arm or a leg reads in front of a prop
            '<filter id="kbm-cut" x="-30%" y="-30%" width="160%" height="160%">'
            '<feMorphology in="SourceAlpha" operator="dilate" radius="2.2" result="fat"/><feFlood/>'
            '<feComposite in2="fat" operator="in" result="ring"/>'
            '<feMerge><feMergeNode in="ring"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>') if dots else ""
    return (f'<svg viewBox="0 0 160 {CELL * len(gags)}" focusable="false" aria-hidden="true">'
            f'{defs}{cells}</svg>')


def html() -> str:
    """Both margins, as they go just inside <body>."""
    return (f'<div class="kbm kbm-l" aria-hidden="true">{column((courier, gardener, dozer), dots=True)}</div>'
            f'<div class="kbm kbm-r" aria-hidden="true">{column((caller, stamper, climber))}</div>')


CSS = f"""
.kbm{{display:none}}
@media screen and (min-width:{WIDTH + 2 * 116}px){{
  .kbm{{display:flex;position:fixed;top:0;bottom:0;z-index:-1;pointer-events:none;align-items:center;justify-content:center;
    width:calc((100vw - {WIDTH}px) / 2 - 14px);color:var(--tone)}}
  .kbm-l{{left:0}}
  .kbm-r{{right:0}}
  .kbm svg{{width:min(100%,190px);height:auto;max-height:calc(100vh - 32px);fill:currentColor;overflow:visible}}
  .kbm .l{{fill:none;stroke:currentColor;stroke-linecap:round;stroke-linejoin:round}}
  .kbm .s{{opacity:.75}}
  .kbm .t{{opacity:.22}}
  .kbm .c{{fill:none;stroke:var(--bg);stroke-linecap:round;stroke-linejoin:round}}
  .kbm .r{{fill:var(--seal)}}
  .kbm .rr{{fill:none;stroke:var(--seal);stroke-linecap:round;stroke-linejoin:round}}
  .kbm .g{{fill:var(--gold)}}
  .kbm feFlood{{flood-color:var(--bg)}}
}}
"""


def inject(page: str) -> str:
    """The page with the cartoons just inside <body> and their look before </head>."""
    page = page.replace("</head>", f'<style id="kb-margins">{CSS}</style></head>', 1)
    i = page.find("<body")
    if i < 0:
        return page
    j = page.index(">", i) + 1
    return page[:j] + html() + page[j:]
