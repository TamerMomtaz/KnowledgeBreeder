"""kb's look, the night edition: ink and screentone, a red seal for what you decide, gold for what you have earned.

Every page kb draws (the advice page, the list of runs, the town, the plant walk) takes the same layer, laid over
its own style, so the pages stay readable without it. Nothing is fetched: the fonts are the ones on your machine.

The game part counts only what you did. A review is one model's answer you rated; every five reviews is a level. A
streak is the days in a row that hold a run you rated. A model's rank is how often you would act on its advice.
"""

from __future__ import annotations

import html
from datetime import date, timedelta

STEP = 5                                                   # reviews per level
RANKS = ((0.70, "S"), (0.50, "A"), (0.35, "B"), (0.20, "C"), (0.0, "D"))

CSS = r"""
:root{
  --bg:#e4e3de; --ink:#17181f; --soft:#565866; --line:#17181f2e; --card:#f4f3ef; --on:#f5dcd6; --warn:#8f5200;
  --accent:#2f6b6d; --accent-ink:#ffffff; --tied:#b8282e; --seal:#b8282e; --seal-ink:#ffffff; --gold:#7a5c22;
  --frame:#17181f; --drop:#17181f; --tone:#17181f; --speed:#17181f30; --shadow:4px 4px 0 var(--drop);
  --wall-l:#dcdad3; --wall-r:#c9c6bd; --win:#a9a69c; --lit:#c48a1a; --edge:#17181f; --plate-l:86%; --roof-s:34%;
  --roof-l:56%; --slab-l:72%; --lane:#17181f14; --pipe:#2f6b6d; --fill:#dddbd4; --tint:#d5e3e3; --bad:#b3261e;
  --display:"Bahnschrift","Avenir Next Condensed","Roboto Condensed","Arial Narrow","DejaVu Sans Condensed","Noto Sans",system-ui,sans-serif;
  --serif:"Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,"Noto Serif","DejaVu Serif",serif;
  --kufi:"Noto Kufi Arabic","Geeza Pro","Segoe UI","Noto Sans Arabic",Tahoma,sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#141722; --ink:#ece6d6; --soft:#a3a5b4; --line:#ece6d624; --card:#1d2130; --on:#3b1f27; --warn:#e8b04a;
    --accent:#6fb3b3; --accent-ink:#0c1416; --tied:#e2474d; --seal:#e2474d; --seal-ink:#140c0e; --gold:#d2b06e;
    --frame:#d9d1bd; --drop:#05060a; --tone:#ece6d6; --speed:#ece6d62c; --shadow:5px 5px 0 var(--drop);
    --wall-l:#2c3245; --wall-r:#232838; --win:#151826; --lit:#d2b06e; --edge:#05060a; --plate-l:17%; --roof-s:35%;
    --roof-l:45%; --slab-l:12%; --lane:#ffffff10; --pipe:#6fb3b3; --fill:#262b3d; --tint:#1f3640; --bad:#ff6b6b;
  }
}
body{background:var(--bg);color:var(--ink)}
::selection{background:var(--seal);color:var(--seal-ink)}
:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
a{color:var(--accent)}

/* the title card */
header{position:relative;isolation:isolate;display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:24px;
  align-items:center;border:2px solid var(--frame);box-shadow:var(--shadow);
  padding:20px 22px 26px;margin:4px 0 22px;overflow:hidden;--at:22% 42%;
  background:radial-gradient(ellipse 40% 56% at var(--at),var(--card) 46%,transparent 100%),
    repeating-conic-gradient(from 1deg at var(--at),var(--speed) 0 .35deg,transparent .35deg 2.3deg),
    repeating-conic-gradient(from 0deg at var(--at),var(--speed) 0 .9deg,transparent .9deg 6.7deg),var(--card)}
[dir=rtl] header{--at:78% 42%}
header>*{grid-column:1;min-width:0}
header::before{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;opacity:.2;
  background-image:radial-gradient(circle,var(--tone) 1.05px,transparent 1.35px);background-size:7px 7px;
  -webkit-mask-image:linear-gradient(110deg,transparent 30%,#000 96%);mask-image:linear-gradient(110deg,transparent 30%,#000 96%)}
[dir=rtl] header::before{-webkit-mask-image:linear-gradient(250deg,transparent 30%,#000 96%);mask-image:linear-gradient(250deg,transparent 30%,#000 96%)}
header::after{content:"";position:absolute;inset-inline-start:0;bottom:0;width:min(46%,420px);height:7px;background:var(--seal);
  transform-origin:left center}
[dir=rtl] header::after{transform-origin:right center}
header h1,.top h1{font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:clamp(2rem,6.4vw,3.5rem);
  line-height:.98;letter-spacing:-.015em;margin:0 0 8px;text-shadow:.045em .045em 0 var(--seal)}
[lang="ar"] header h1,[lang="ar"] .top h1{font-family:var(--kufi);font-size:clamp(1.7rem,5.4vw,2.8rem);line-height:1.2;letter-spacing:0}
header p{color:var(--soft)}
[lang="en"] header>p:not(.back):not(.sign),[lang="en"] header>.sub{font-family:var(--serif);font-style:italic;font-size:1.06rem}
header .sign{color:var(--ink);font-weight:600}
.top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}

/* the status window */
.hud{grid-column:2;grid-row:1/span 8;display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 14px;align-items:center;
  min-width:250px;max-width:340px;padding:12px 14px;background:var(--bg);border:2px solid var(--frame);box-shadow:3px 3px 0 var(--gold)}
.hud .lv{grid-row:1/span 3;display:grid;place-items:center;width:64px;height:64px;border:2px solid var(--gold);border-radius:50%;
  color:var(--gold);font-family:var(--display);font-stretch:condensed;font-weight:800;line-height:1;text-align:center}
.hud .lv small{display:block;font-size:.72rem;font-weight:700;letter-spacing:.02em}
.hud .lv b{display:block;font-size:1.9rem}
.hud .what{margin:0;font-weight:700;color:var(--ink)}
.hud .cells{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin:2px 0}
.hud .cells i{display:block;height:9px;border:1.5px solid var(--frame);transform:skewX(-18deg);background:transparent}
.hud .cells i.f{background:var(--gold);border-color:var(--gold)}
.hud .note{margin:0;color:var(--soft);font-size:.86rem;line-height:1.35}
.hud .streak{color:var(--seal);font-weight:700}
header{container-type:inline-size}
@container (max-width:780px){
  header>*,header>.hud{grid-column:1/-1}
  .hud{grid-row:auto;margin-top:14px;max-width:none}
}

/* panels: ink frames and hard shadows */
.box,.district,.scene,.panel,.rep .card{border:2px solid var(--frame);border-radius:3px;box-shadow:var(--shadow);background:var(--card)}
.piece{background:var(--card);border:2px solid var(--frame);border-inline-start:7px solid hsl(var(--hue) 55% 52%);
  border-radius:3px;box-shadow:var(--shadow)}
.piece.on{background:var(--on)}
section.group{border:2px dashed var(--soft);border-radius:3px}
h2,.district h2,.panel h2{font-family:var(--display);font-stretch:condensed;font-weight:800;letter-spacing:.005em}
.box>h2:first-child{width:fit-content;max-width:calc(100% + 16px);margin-block:-14px 12px;margin-inline:-16px 0;
  padding:6px 30px 7px 16px;background:var(--frame);color:var(--card);font-size:1.08rem;line-height:1.25;
  clip-path:polygon(0 0,100% 0,calc(100% - 14px) 100%,0 100%)}
[dir=rtl] .box>h2:first-child{padding:6px 16px 7px 30px;clip-path:polygon(0 0,100% 0,100% 100%,14px 100%)}
[lang="ar"] h2,[lang="ar"] .district h2,[lang="ar"] .panel h2{font-family:var(--kufi);letter-spacing:0}
.move{font-size:1.12rem}
[lang="en"] .why,[lang="en"] .said span{font-family:var(--serif);font-style:italic}
.kind,.panel h3{text-transform:none;letter-spacing:0}
.inbox .note{position:relative;justify-self:start;width:fit-content;max-width:100%;margin:8px 0 4px;padding:5px 14px;
  background:var(--bg);border:1.5px solid var(--frame);border-radius:16px}
.inbox .note::before{content:"";position:absolute;inset-inline-start:18px;top:-6.5px;width:10px;height:10px;background:var(--bg);
  border-top:1.5px solid var(--frame);border-inline-start:1.5px solid var(--frame);transform:rotate(45deg)}
[dir=rtl] .inbox .note::before{transform:rotate(-45deg)}
.inbox .kind{align-self:start;justify-self:start;padding:1px 8px;border:1.5px solid var(--frame);font-family:var(--display);
  font-stretch:condensed;font-size:.86rem;font-weight:800}
[lang="ar"] .inbox .kind{font-family:var(--kufi);font-weight:700}
.runs .date{font-family:var(--display);font-stretch:condensed;font-weight:800}
.kind{border-radius:2px}
.panel h3{font-size:.95rem;color:var(--soft)}
.tag{border-radius:2px}

/* what you decide wears the seal */
.tick{border:2px solid var(--frame);border-radius:3px;background:var(--bg)}
.tick:has(input:checked){background:var(--on);border-color:var(--seal);box-shadow:3px 3px 0 var(--seal)}
.tick:has(input:checked)::after{content:"\2713";margin-inline-start:auto;flex:none;width:32px;height:32px;border:2.5px solid var(--seal);
  border-radius:50%;display:grid;place-items:center;color:var(--seal);font-weight:900;transform:rotate(-14deg)}
.tick input,.none input,.radio input,.keep input{accent-color:var(--seal)}
.copy,.save,#add,#send,.act,.btn[aria-pressed="true"],.chip[aria-pressed="true"],.pick.sel{
  background:var(--seal);border-color:var(--seal);color:var(--seal-ink)}
.copy,.save,#add,#send,#attach,#rec,.act{position:relative;isolation:isolate;background:transparent;border:0;border-radius:0;
  box-shadow:none;padding-inline:22px}
.copy::before,.save::before,#add::before,#send::before,#attach::before,#rec::before,.act::before{content:"";position:absolute;inset:0;z-index:-1;
  background:var(--seal);box-shadow:4px 4px 0 var(--drop);transform:skewX(-14deg)}
#attach::before,#rec::before,.act.alt::before{background:var(--card);border:1.5px solid var(--frame);box-shadow:3px 3px 0 var(--drop)}
#rec[aria-pressed="true"]::before{background:var(--seal);border-color:var(--seal)}
.act.alt{color:var(--ink)}
[dir=rtl] :is(.copy,.save,#add,#send,#attach,#rec,.act)::before{transform:skewX(14deg)}
:is(.copy,.save,#add,#send,#attach,#rec,.act):focus-visible{outline-offset:7px}
:is(.copy,.save,#add,#send,#attach,#rec,.act):active:not(:disabled){transform:translate(2px,2px)}
:is(.copy,.save,#add,#send,#attach,#rec,.act):active:not(:disabled)::before{box-shadow:1px 1px 0 var(--drop)}
.btn,.chip,.lang,.close,.bar select,.bar input,.pick,input.reason,.change-text,textarea{border-radius:3px}
.btn,.chip,.lang,.close{border:1.5px solid var(--frame)}
.tab[aria-selected="true"]{border-bottom-color:var(--seal)}
.just{outline-color:var(--seal)}
.state.done{color:var(--gold)}
.state.todo{color:var(--seal)}
.star{color:var(--gold)}
.seal-r{display:inline-grid;place-items:center;width:22px;height:22px;margin-inline-start:6px;vertical-align:middle;
  border:1.5px solid var(--gold);border-radius:50%;color:var(--gold);font:800 .78rem/1 var(--display)}
.seal-r.r-S{background:var(--gold);color:var(--card)}
.seal-r.r-none{border-style:dashed;color:var(--soft);border-color:var(--soft)}
.ranks{margin:8px 0 0}
.runs a:hover .who,.runs a:focus-visible .who{color:var(--seal)}

/* one moment on arrival: the slash is drawn, the gauge fills */
@media (prefers-reduced-motion: no-preference){
  header::after{animation:kb-slash .7s cubic-bezier(.2,.8,.2,1) .1s both}
  .hud .cells i.f{animation:kb-fill .35s ease-out both}
  .hud .cells i.f:nth-child(2){animation-delay:.45s}.hud .cells i.f:nth-child(3){animation-delay:.55s}
  .hud .cells i.f:nth-child(4){animation-delay:.65s}.hud .cells i.f:nth-child(1){animation-delay:.35s}
  .tick:has(input:checked)::after{animation:kb-stamp .22s cubic-bezier(.3,1.6,.5,1) both}
}
@keyframes kb-slash{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes kb-fill{from{background:transparent}}
@keyframes kb-stamp{from{transform:scale(1.7) rotate(-14deg);opacity:0}to{transform:scale(1) rotate(-14deg);opacity:1}}
@media print{header{box-shadow:none}header::before,header::after{display:none}.box,.piece,.district,.scene,.panel{box-shadow:none}}
"""

LABELS = {
    "en": {
        "hud": "Your record", "lv": "Level", "level": "Level {n}", "reviews": "{n} reviews so far.",
        "to_next": "{k} more to level {n}.", "to_next_1": "1 more to level {n}.",
        "streak": "{n}-day streak.", "streak_1": "1-day streak.",
        "no_streak": "Rate a run today to start a streak.",
        "how": "A review is one model's answer you rated. Every five reviews is a level.",
        "rank": "Rank {r}: you would act on {p}% of its advice, over {n} rated runs.",
        "rank_1": "Rank {r}: you would act on {p}% of its advice, over 1 rated run.",
        "unranked": "Not ranked yet: rate one of its runs.",
        "ranks_note": "A model's rank is how often you would act on its advice: S at 70% or more, A at 50%, B at 35%, "
                      "C at 20%, D below that.",
    },
    "ar": {
        "hud": "سجلّك", "lv": "مستوى", "level": "المستوى {n}", "reviews": "التقييمات حتى الآن: {n}.",
        "to_next": "باقي {k} للمستوى {n}.", "to_next_1": "باقٍ تقييم واحد للمستوى {n}.",
        "streak": "أيام متتالية: {n}.", "streak_1": "يوم واحد متتالٍ.",
        "no_streak": "قيّم تشغيلاً اليوم لتبدأ سلسلة.",
        "how": "التقييم هو إجابة نموذج واحد قيّمتها. كل خمسة تقييمات مستوى.",
        "rank": "الرتبة {r}: ستعمل بـ {p}٪ من نصائحه، في {n} تشغيلات مقيّمة.",
        "rank_1": "الرتبة {r}: ستعمل بـ {p}٪ من نصائحه، في تشغيل مقيّم واحد.",
        "unranked": "بلا رتبة بعد: قيّم أحد تشغيلاته.",
        "ranks_note": "رتبة النموذج هي كم مرة ستعمل بنصيحته: S عند ٧٠٪ أو أكثر، و A عند ٥٠٪، و B عند ٣٥٪، "
                      "و C عند ٢٠٪، و D أقل من ذلك.",
    },
}


def _t(lang: str, key: str, **v) -> str:
    s = LABELS.get(lang, LABELS["en"]).get(key) or LABELS["en"][key]
    for k, x in v.items():
        s = s.replace("{" + k + "}", f"\u2068{x}\u2069" if lang == "ar" else str(x))
    return s


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def inject(page: str) -> str:
    """The page with kb's look laid over its own style."""
    return page.replace("</head>", f'<style id="kb-look">{CSS}</style></head>', 1)


def rank(share: float | None) -> str:
    if share is None:
        return ""
    return next(r for floor, r in RANKS if share >= floor)


def standing(hist: list[dict], today: date | None = None) -> dict:
    """Your record from the runs you rated (page.history rows): reviews, level, streak, and each model's rank."""
    today = today or date.today()
    reviews, days, shares = 0, set(), {}
    for r in hist:
        rated = [w for w, s in r["workers"].items() if s.get("would_act") is not None]
        reviews += len(rated)
        if rated:
            days.add(r["date"])
        for w in rated:
            shares.setdefault(w, []).append(r["workers"][w]["would_act"])
    streak, day = 0, today if today.isoformat() in days else today - timedelta(days=1)
    while day.isoformat() in days:
        streak, day = streak + 1, day - timedelta(days=1)
    models = {w: {"rank": rank(sum(v) / len(v)), "share": sum(v) / len(v), "runs": len(v)} for w, v in shares.items()}
    return {"reviews": reviews, "level": reviews // STEP + 1, "into": reviews % STEP, "streak": streak, "models": models}


def hud(st: dict, lang: str = "en") -> str:
    """The status window for a page's title card."""
    k, nxt = STEP - st["into"], st["level"] + 1
    cells = "".join('<i class="f"></i>' if i < st["into"] else "<i></i>" for i in range(STEP))
    streak = (_t(lang, "streak", n=st["streak"]) if st["streak"] > 1 else
              _t(lang, "streak_1") if st["streak"] == 1 else _t(lang, "no_streak"))
    return (f'<aside class="hud" aria-label="{_e(_t(lang, "hud"))}">'
            f'<div class="lv" aria-hidden="true"><small>{_e(_t(lang, "lv"))}</small><b>{st["level"]}</b></div>'
            f'<p class="what">{_e(_t(lang, "level", n=st["level"]))}</p>'
            f'<div class="cells" role="progressbar" aria-valuemin="0" aria-valuemax="{STEP}" aria-valuenow="{st["into"]}" '
            f'aria-label="{_e(_t(lang, "to_next_1" if k == 1 else "to_next", k=k, n=nxt))}">{cells}</div>'
            f'<p class="note">{_e(_t(lang, "reviews", n=st["reviews"]) if st["reviews"] else _t(lang, "how"))} '
            f'{_e(_t(lang, "to_next_1" if k == 1 else "to_next", k=k, n=nxt))} '
            f'<span{" class=" + chr(34) + "streak" + chr(34) if st["streak"] else ""}>{_e(streak)}</span></p></aside>')


def seal(worker: str, st: dict | None, lang: str = "en") -> str:
    """A model's rank as a small seal, with what it means in words for a screen reader and on hover."""
    if st is None:
        return ""
    m = st["models"].get(worker)
    if not m:
        return f'<span class="seal-r r-none" role="img" aria-label="{_e(_t(lang, "unranked"))}" title="{_e(_t(lang, "unranked"))}">·</span>'
    say = _t(lang, "rank_1" if m["runs"] == 1 else "rank", r=m["rank"], p=round(100 * m["share"]), n=m["runs"])
    return f'<span class="seal-r r-{m["rank"]}" role="img" aria-label="{_e(say)}" title="{_e(say)}">{m["rank"]}</span>'


def ranks_note(lang: str = "en") -> str:
    return f'<p class="soft small ranks">{_e(_t(lang, "ranks_note"))}</p>'
