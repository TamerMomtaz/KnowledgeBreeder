"""What each box and button does, in English and Arabic, on the page itself and read aloud.

Every box on kb's first page gets a small ? in its corner. It opens a speech bubble that says what the box is, how to
use it, and what each of its buttons does. The first page also opens with "How to use kb", and the advice page with
"How this page works". A Read aloud button reads the bubble with the voice the phone or laptop already has (the
browser's own speech, so nothing is sent anywhere). The words name the buttons as the page does, so the two never
drift apart: the page's labels are passed in.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

TEXT = {
    "en": {
        "q": "?", "help": "What is {box}?", "speak": "Read aloud", "stop": "Stop reading",
        "no_voice": "This device has no English voice. Add one in its text-to-speech settings.",
        "guide": "How to use kb", "run_guide": "How this page works",
        "steps": [
            ("Add your cards. In Ask kb, press Add cards from a file and pick a cards file. kb keeps them as the "
            "picture of your work."),
            ("Send kb everything. Paste, attach or record in Your inbox. On the phone, press Share in any app and "
            "pick kb."),
            "Read the top of the page. Coming up and Where your work waits come from your cards, with no model.",
            ("Ask for advice. Then open the run, tick what you would act on, and pick the better answer. Your ticks "
            "teach kb which model to trust."),
            "Turn on phone reminders, so kb tells you before a deadline.",
            "Press ? on any box to read or hear what it does.",
        ],
        "run_steps": [
            ("Read each piece. Each is one idea from one model, with the lines of your cards it rests on. Check them "
            "before you act."),
            "In Record what you think, tick each piece you would act on, or tick None of these.",
            "Write why in a few words, if you like.",
            ("To say an idea your way, open Change it under the idea. Tick Keep it as a lesson for every run to make "
            "your change a rule."),
            "When more than one model answered, choose which answer is better overall.",
            "Press Save. Each answer is saved once. Your ticks rank the models and fill your level.",
        ],
        "boxes": {
            "soon": {
                "what": "The dates written on your cards, and the closing dates of chances kb found in your inbox, "
                        "nearest first.",
                "how": "A line that says Slipped is a deadline that passed while the thing is still open. Nothing to "
                       "press here. To add a date, write it on the card, for example \"due 2026-12-10\" or \"before "
                       "10 December 2026\", then add the cards file again.",
            },
            "inbox": {
                "what": "Everything you send kb: posts, links, screenshots, PDFs, Word files and voice notes. It all "
                        "stays on this laptop.",
                "how": "Type or paste in the box, add files if you like, then press Send to kb. A few words sent with "
                       "files become their note. A cards file sent here goes into your picture instead.",
                "buttons": [("attach", "Pick files from this phone or laptop, up to 20 MB each."),
                            ("record", "Records until you press Stop recording."),
                            ("send", "Keeps the words and the files in your inbox. Sending twice is safe.")],
            },
            "waits": {
                "what": "Worked out from your cards with no model: which needs wait on you and on others, how long "
                        "things wait, and which cards went quiet.",
                "how": "Start with what waits on you: only you can move it. A card one step from free needs just one "
                       "thing. Quiet cards are old work to build on. Change a card and add the cards file again, and "
                       "this box changes with it.",
            },
            "where": {
                "what": "The pages you visited, what you searched and asked AI, and the files you opened or changed, "
                        "so you can find where you left off.",
                "how": "It stays off until you press Show where I was. kb reads it on this laptop each time, keeps "
                       "none of it, and sends nothing anywhere.",
                "buttons": [("where_on", "Turns this box on."),
                            ("where_all", "Opens the full list, with a search.")],
            },
            "ask": {
                "what": "The buttons that used to need the terminal. Each one runs here on the laptop, and you can "
                        "leave the page while kb works.",
                "how": ("Advice asks every model you like: the ones on this laptop, and each paid one you keep a key "
                        "for, while today's spend stays under your daily cap ($1 until you change it). To add a paid "
                        "model, type kb keys add on the laptop, followed by openai, gemini, kimi, deepseek or claude. "
                        "Lines that are private never leave the laptop."),
                "buttons": [("b_advise", ("Your models read your cards, and each suggests what to do next. Open the "
                                         "run to rate the answers.")),
                            ("b_scout", ("kb reads your inbox for calls, grants and offers that fit your cards, with "
                                        "their closing dates.")),
                            ("b_cards", ("Pick a cards file. kb adds new cards and updates the ones it knows, then "
                                        "says what changed.")),
                            ("l_check", "Shows which cards are ready, thin or weak, and what each one lacks."),
                            ("l_chances", "The chances kb found in your inbox, open ones first.")],
            },
            "nudge": {
                "what": "kb sends your phone a morning note and a reminder before each deadline, through the free "
                        "ntfy app.",
                "how": "Press Turn on phone reminders, then follow the three steps in this box on your phone.",
                "buttons": [("nudge_on", "Makes your own private topic and starts the reminders."),
                            ("nudge_test", "Sends one note, to check that your phone gets it."),
                            ("nudge_off", "Stops every note. Your topic is kept for next time.")],
            },
            "ideas": {
                "what": "One ledger of every idea, lesson, check and book principle kb has read: from your cards, and "
                        "from the journey and KB thinks files you added. Each line says where it came from.",
                "how": "Answer the oldest lines first. Your answers teach kb what to bring back, and the two numbers "
                       "at the top say whether its ideas are helping you. To add a file, use Add cards from a file: a "
                       "file with no cards in it is kept as ideas.",
                "buttons": [("i_useful", "Keeps the line under Useful, so kb brings it back."),
                            ("i_later", "Moves it out of the way for now."),
                            ("i_done", "You applied it. It counts in Done in 30 days.")],
            },
            "books": {
                "what": "The frame-outer, kb's agent for books. A title becomes four things: the book's framework (its "
                        "principles), a platform of its own, features for the platforms on your cards, and a song "
                        "that carries the ideas.",
                "how": "Write titles, one a line, or send book: and the title to your inbox: the router hands it here. "
                       "It works from what the model knows of the book, not your Audible clips, and says when it does "
                       "not know a book. Its lines land in Your ideas, where you tick what rings true.",
                "buttons": [("b_frame", "Puts the titles on the shelf and frames every book that waits, up to five a "
                                        "press, with the best model kb may ask under your daily cap.")],
            },
            "grow": {
                "what": "kb's own to-do list, taken from your cards: what is unfinished on kb's card, and the parts and "
                        "ideas on other cards that name kb.",
                "how": "Answer each new line. The build list is what gets built next: Send to Claude hands it to "
                       "Claude on GitHub, which builds it and opens a pull request for you to merge. Mark a line Done "
                       "once kb has it. A line you answered stays answered when you add the cards again.",
                "buttons": [("g_build", "Puts the line on the build list."),
                            ("g_later", "Moves it out of the way. It waits under Not now."),
                            ("g_done", "Takes it off the build list once kb has it."),
                            ("g_send", "Opens one public GitHub issue with the lines not sent before, asking Claude "
                                       "to build them. Lines that name anything private stay on this laptop. Needs "
                                       "kb keys add github once."),
                            ("g_copy", "Copies the build list as plain text, with the card each line came from.")],
            },
            "runs": {
                "what": "Every time you asked for advice, newest first, with who answered and how many answers you "
                        "rated.",
                "how": "Open a run to read the answers, tick what you would act on, and pick the better one. Each "
                       "rated answer counts toward your level at the top.",
            },
            "lessons": {
                "what": "Short rules that every advice run follows, in your own words.",
                "how": "Write one rule in the box, for example \"Suggest free tools first\", and press Add lesson. It "
                       "counts from the next run. A change you keep as a lesson while rating is added here too.",
                "buttons": [("add", "Saves the rule.")],
            },
        },
    },
    "ar": {
        "q": "؟", "help": "ما هو «{box}»؟", "speak": "اقرأ بصوت عالٍ", "stop": "أوقف القراءة",
        "no_voice": "لا يوجد صوت عربي على هذا الجهاز. أضِفه من إعدادات تحويل النص إلى كلام.",
        "guide": "كيف تستخدم kb", "run_guide": "كيف تعمل هذه الصفحة",
        "steps": [
            "أضف بطاقاتك. في «اسأل kb» اضغط «أضف بطاقات من ملف» واختر ملف البطاقات. يحفظها kb صورةً لعملك.",
            "أرسل كل شيء إلى kb. الصق أو أرفق أو سجّل في «صندوقك». على الهاتف، اضغط «مشاركة» في أي تطبيق واختر kb.",
            "اقرأ أعلى الصفحة. «قريبًا» و«أين ينتظر عملك» محسوبان من بطاقاتك دون أي نموذج.",
            ("اطلب نصيحة. ثم افتح التشغيل، وضع علامة على ما ستعمل به، واختر الإجابة الأفضل. علاماتك تعلّم kb بأي "
            "نموذج يثق."),
            "شغّل تذكيرات الهاتف، ليخبرك kb قبل كل موعد نهائي.",
            "اضغط ؟ على أي صندوق لتقرأ أو تسمع ما يفعله.",
        ],
        "run_steps": [
            "اقرأ كل قطعة. كل قطعة فكرة واحدة من نموذج واحد، مع سطور بطاقاتك التي تستند إليها. راجعها قبل أن تعمل.",
            "في «سجّل رأيك»، ضع علامة على كل قطعة ستعمل بها، أو على «لا شيء من هذه».",
            "اكتب السبب في كلمات قليلة إن شئت.",
            "لتقول فكرة بطريقتك، افتح «غيّرها» تحت الفكرة. ضع علامة على «احفظها درساً لكل تشغيل» لتصبح قاعدة.",
            "إذا أجاب أكثر من نموذج، اختر الإجابة الأفضل إجمالًا.",
            "اضغط «حفظ». تُحفظ كل إجابة مرة واحدة. علاماتك ترتّب النماذج وتملأ مستواك.",
        ],
        "boxes": {
            "soon": {
                "what": "التواريخ المكتوبة على بطاقاتك، ومواعيد إغلاق الفرص التي وجدها kb في صندوقك، الأقرب أولًا.",
                "how": "السطر المكتوب فيه «فات موعده» موعد نهائي مرّ والأمر ما زال مفتوحًا. لا شيء تضغطه هنا. لتضيف "
                       "تاريخًا، اكتبه على البطاقة بالإنجليزية، مثل \u2068\"due 2026-12-10\"\u2069 أو \u2068\"before "
                       "10 December 2026\"\u2069، ثم أضف ملف البطاقات مرة أخرى.",
            },
            "inbox": {
                "what": "كل ما ترسله إلى kb: منشورات وروابط ولقطات شاشة وملفات PDF وWord ورسائل صوتية. كلها تبقى على "
                        "هذا اللابتوب.",
                "how": "اكتب أو الصق في المربع، وأضف ملفات إن شئت، ثم اضغط «أرسل إلى kb». الكلمات المرسلة مع الملفات "
                       "تصبح ملاحظتها. ملف البطاقات المرسل هنا يدخل صورتك بدلًا من الصندوق.",
                "buttons": [("attach", "اختر ملفات من هذا الهاتف أو اللابتوب، حتى 20 ميجابايت لكل ملف."),
                            ("record", "يسجّل حتى تضغط «أوقف التسجيل»."),
                            ("send", "يحفظ الكلمات والملفات في صندوقك. الإرسال مرتين لا يضر.")],
            },
            "waits": {
                "what": "محسوب من بطاقاتك دون أي نموذج: أي الاحتياجات تنتظرك وأيها ينتظر غيرك، وكم تنتظر الأشياء، وأي "
                        "البطاقات هدأت.",
                "how": "ابدأ بما ينتظرك: لا يحرّكه أحد غيرك. البطاقة التي على بُعد خطوة تحتاج شيئًا واحدًا فقط. البطاقات "
                       "الهادئة عمل قديم تبني عليه. غيّر بطاقة وأضف ملف البطاقات مرة أخرى، فيتغيّر هذا الصندوق معها.",
            },
            "where": {
                "what": "الصفحات التي زرتها، وما بحثت عنه وسألت عنه الذكاء الاصطناعي، والملفات التي فتحتها أو غيّرتها، "
                        "لتجد أين توقفت.",
                "how": "يبقى مغلقًا حتى تضغط «اعرض أين كنت». يقرأ kb ذلك على هذا اللابتوب في كل مرة، ولا يحتفظ بشيء "
                       "منه، ولا يرسل شيئًا إلى أي مكان.",
                "buttons": [("where_on", "يشغّل هذا الصندوق."),
                            ("where_all", "يفتح القائمة كاملة مع البحث.")],
            },
            "ask": {
                "what": "الأزرار التي كانت تحتاج الطرفية. كل زر يعمل هنا على اللابتوب، ويمكنك مغادرة الصفحة بينما يعمل "
                        "kb.",
                "how": ("تسأل النصيحة كل نموذج تحبه: نماذج هذا اللابتوب، وكل نموذج مدفوع تحفظ له مفتاحًا، ما دام إنفاق "
                        "اليوم تحت سقفك اليومي (دولار واحد حتى تغيّره). لإضافة نموذج مدفوع اكتب على اللابتوب kb keys "
                        "add ثم اسم المزوّد: openai أو gemini أو kimi أو deepseek أو claude. السطور الخاصة لا تغادر "
                        "اللابتوب أبدًا."),
                "buttons": [("b_advise", ("تقرأ نماذجك بطاقاتك، ويقترح كل منها ما تفعله بعد ذلك. افتح التشغيل لتقيّم "
                                         "الإجابات.")),
                            ("b_scout", "يقرأ kb صندوقك بحثًا عن دعوات ومنح وعروض تناسب بطاقاتك، مع مواعيد إغلاقها."),
                            ("b_cards", "اختر ملف بطاقات. يضيف kb البطاقات الجديدة ويحدّث ما يعرفه، ثم يقول ما تغيّر."),
                            ("l_check", "يبيّن أي البطاقات جاهزة أو رقيقة أو ضعيفة، وما ينقص كلًّا منها."),
                            ("l_chances", "الفرص التي وجدها kb في صندوقك، المفتوحة أولًا.")],
            },
            "nudge": {
                "what": "يرسل kb إلى هاتفك رسالة صباحية وتذكيرًا قبل كل موعد نهائي، عبر تطبيق ntfy المجاني.",
                "how": "اضغط «شغّل تذكيرات الهاتف»، ثم اتبع الخطوات الثلاث في هذا الصندوق على هاتفك.",
                "buttons": [("nudge_on", "ينشئ موضوعك الخاص ويبدأ التذكيرات."),
                            ("nudge_test", "يرسل رسالة واحدة لتتأكد أن هاتفك يستقبلها."),
                            ("nudge_off", "يوقف كل الرسائل. يبقى موضوعك محفوظًا للمرة القادمة.")],
            },
            "ideas": {
                "what": "سجل واحد لكل فكرة ودرس وفحص ومبدأ من كتاب قرأه kb: من بطاقاتك، ومن ملفات الرحلة وملفات «KB "
                        "يفكر» التي أضفتها. كل سطر يذكر مصدره.",
                "how": "أجب عن الأسطر الأقدم أولًا. إجاباتك تعلّم kb ما يعيده إليك، والرقمان في الأعلى يقولان هل أفكاره "
                       "تساعدك. لإضافة ملف استخدم «أضف بطاقات من ملف»: الملف الذي لا بطاقات فيه يُحفظ أفكارًا.",
                "buttons": [("i_useful", "يحفظ السطر تحت «مفيد» ليعيده kb إليك."),
                            ("i_later", "يبعده عن الطريق الآن."),
                            ("i_done", "طبّقته. يُحسب في «تم في 30 يومًا».")],
            },
            "books": {
                "what": "مُستخرِج الإطار، وكيل kb للكتب. العنوان يصير أربعة أشياء: إطار الكتاب (مبادئه)، ومنصة خاصة "
                        "به، وميزات للمنصات التي على بطاقاتك، وأغنية تحمل أفكاره.",
                "how": "اكتب العناوين، عنوانًا في كل سطر، أو أرسل إلى صندوقك كتاب: ثم العنوان، فيسلّمه الموزّع إلى هنا. "
                       "يعمل مما يعرفه النموذج عن الكتاب لا من مقاطعك في Audible، ويقول حين لا يعرف كتابًا. أسطره تذهب "
                       "إلى «أفكارك» حيث تعلّم ما يبدو لك صحيحًا.",
                "buttons": [("b_frame", "يضع العناوين على الرف ويستخرج إطار كل كتاب ينتظر، حتى خمسة في كل ضغطة، "
                                        "بأفضل نموذج يُسمح لـ kb بسؤاله تحت سقفك اليومي.")],
            },
            "grow": {
                "what": "قائمة مهام kb نفسه، مأخوذة من بطاقاتك: ما لم ينتهِ على بطاقة kb، والأجزاء والأفكار على البطاقات "
                        "الأخرى التي تذكر kb.",
                "how": "أجب عن كل سطر جديد. قائمة البناء هي ما يُبنى بعد ذلك: «أرسلها إلى Claude» يسلّمها إلى Claude على "
                       "GitHub فيبنيها ويفتح طلب دمج لتدمجه أنت. علّم السطر «تم» حين يصبح في kb. السطر الذي أجبت عنه "
                       "يبقى كما هو حين تضيف البطاقات مرة أخرى.",
                "buttons": [("g_build", "يضع السطر في قائمة البناء."),
                            ("g_later", "يبعده عن الطريق. ينتظر تحت «ليس الآن»."),
                            ("g_done", "يرفعه من قائمة البناء حين يصبح في kb."),
                            ("g_send", "يفتح تذكرة علنية واحدة على GitHub بالأسطر التي لم تُرسل من قبل، ويطلب من "
                                       "Claude أن يبنيها. الأسطر التي تذكر شيئًا خاصًا تبقى على هذا الحاسوب. يحتاج "
                                       "kb keys add github مرة واحدة."),
                            ("g_copy", "ينسخ قائمة البناء نصًا عاديًا، مع البطاقة التي جاء منها كل سطر.")],
            },
            "runs": {
                "what": "كل مرة طلبت فيها نصيحة، الأحدث أولًا، مع من أجاب وكم إجابة قيّمت.",
                "how": "افتح تشغيلًا لتقرأ الإجابات، وضع علامة على ما ستعمل به، واختر الأفضل. كل إجابة تقيّمها تُحسب في "
                       "مستواك أعلى الصفحة.",
            },
            "lessons": {
                "what": "قواعد قصيرة يتبعها كل تشغيل للنصيحة، بكلماتك أنت.",
                "how": "اكتب قاعدة واحدة في المربع، مثل «اقترح الأدوات المجانية أولًا»، واضغط «أضف الدرس». تُحسب من "
                       "التشغيل التالي. التغيير الذي تحفظه درسًا أثناء التقييم يُضاف هنا أيضًا.",
                "buttons": [("add", "يحفظ القاعدة.")],
            },
        },
    },
}

_BOX = re.compile(r'(<section class="box[^"]*" id="([a-z]+)"[^>]*><h2>(.*?)</h2>)', re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def _e(s: str) -> str:
    return html.escape(str(s), quote=True)


def _t(lang: str) -> dict:
    return TEXT[lang if lang in TEXT else "en"]


def _speak(t: dict) -> str:
    return (f'<p class="ex-say"><button type="button" class="speak" aria-pressed="false" data-say="{_e(t["speak"])}" '
            f'data-stop="{_e(t["stop"])}" data-none="{_e(t["no_voice"])}">{_e(t["speak"])}</button>'
            f'<span class="ex-note" role="status"></span></p>')


def panel(lang: str, key: str, title: str = "", name: Callable[[str], str] | None = None) -> str:
    """The ? and its bubble for one box. ``name`` gives a button's label as the page shows it."""
    t = _t(lang)
    b = t["boxes"][key]
    parts = [f'<p>{_e(b["what"])}</p>']
    if b.get("how"):
        parts.append(f'<p>{_e(b["how"])}</p>')
    if b.get("buttons"):
        parts.append('<dl class="ex-buttons">' + "".join(
            f'<dt><bdi>{_e(name(k) if name else k)}</bdi></dt><dd>{_e(v)}</dd>' for k, v in b["buttons"]) + "</dl>")
    label = t["help"].format(box=title or key)
    return (f'<details class="explain"><summary aria-label="{_e(label)}" title="{_e(label)}">'
            f'<span aria-hidden="true">{t["q"]}</span></summary>'
            f'<div class="ex-body">{"".join(parts)}{_speak(t)}</div></details>')


def guide(lang: str, which: str = "home") -> str:
    """How to use kb (the first page) or How this page works (an advice run), folded until pressed."""
    t = _t(lang)
    title, steps = (t["guide"], t["steps"]) if which == "home" else (t["run_guide"], t["run_steps"])
    return (f'<details class="explain guide" id="how"><summary><span class="q" aria-hidden="true">{t["q"]}</span> '
            f'{_e(title)}</summary><div class="ex-body"><ol>{"".join(f"<li>{_e(s)}</li>" for s in steps)}</ol>'
            f'{_speak(t)}</div></details>')


def add(page: str, lang: str, name: Callable[[str], str] | None = None) -> str:
    """The page with a ? on every box kb has words for. The box's heading stays its first child."""
    boxes = _t(lang)["boxes"]

    def one(m: re.Match) -> str:
        if m[2] not in boxes:
            return m[1]
        title = re.sub(r"\s*\(\d+\)$", "", html.unescape(_TAGS.sub("", m[3])).strip())
        return m[1] + panel(lang, m[2], title, name)
    return _BOX.sub(one, page)


CSS = """
.box:has(>details.explain){position:relative}
.box:has(>details.explain)>h2:first-child{max-width:calc(100% - 36px)}
details.explain>summary{position:absolute;top:7px;inset-inline-end:9px;width:32px;height:32px;display:grid;place-items:center;
  list-style:none;cursor:pointer;border:2px solid var(--frame);border-radius:50%;background:var(--card);color:var(--ink);
  font-weight:900;font-size:1.05rem;line-height:1;box-shadow:2px 2px 0 var(--drop)}
details.explain>summary::-webkit-details-marker{display:none}
details.explain>summary::after{content:"";position:absolute;inset:-7px}
details.explain[open]>summary{background:var(--seal);border-color:var(--seal);color:var(--seal-ink)}
details.explain>summary:focus-visible{outline:2px solid var(--seal);outline-offset:3px}
.ex-body{position:relative;margin:4px 0 14px;padding:10px 14px 6px;background:var(--bg);color:var(--ink);
  border:1.5px solid var(--frame);border-radius:16px;font-size:.96rem;line-height:1.5}
.ex-body::before{content:"";position:absolute;top:-6.5px;inset-inline-end:22px;width:10px;height:10px;background:var(--bg);
  border-top:1.5px solid var(--frame);border-inline-start:1.5px solid var(--frame);transform:rotate(45deg)}
[dir=rtl] .ex-body::before{transform:rotate(-45deg)}
.ex-body p{margin:0 0 8px;overflow-wrap:anywhere}
.ex-body ol{margin:0 0 8px;padding-inline-start:22px}
.ex-body li{margin:0 0 6px}
.ex-buttons{margin:0 0 8px}
.ex-buttons dt{font-weight:700;margin-top:8px}
.ex-buttons dd{margin:0}
.ex-say{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.ex-body .speak{min-height:40px;padding:0 14px;background:var(--card);color:var(--ink);border:1.5px solid var(--frame);
  border-radius:3px;font-weight:600;cursor:pointer;box-shadow:2px 2px 0 var(--drop)}
.ex-body .speak[aria-pressed="true"]{background:var(--seal);border-color:var(--seal);color:var(--seal-ink)}
.ex-note{color:var(--soft);font-size:.9rem}
details.guide{margin:10px 0 0}
details.guide>summary{position:static;display:inline-flex;align-items:center;gap:8px;width:auto;height:auto;min-height:40px;
  padding:0 14px 0 6px;border-radius:3px;font-size:.98rem;font-weight:700}
details.guide>summary::after{display:none}
details.guide>summary .q{display:grid;place-items:center;width:26px;height:26px;border:2px solid currentColor;border-radius:50%}
details.guide .ex-body::before{inset-inline-end:auto;inset-inline-start:22px}
"""

JS = """(function(){
  var syn = window.speechSynthesis, on = null, left = 0, seq = 0;
  var all = document.querySelectorAll(".ex-body .speak");
  if (!syn || !window.SpeechSynthesisUtterance){ for (var i = 0; i < all.length; i++) all[i].hidden = true; return; }
  var lang = (document.documentElement.lang || "en").slice(0, 2);
  syn.getVoices();                                       // Chrome fills the list a moment later
  function reset(){ if (on){ on.textContent = on.getAttribute("data-say"); on.setAttribute("aria-pressed", "false"); on = null; } }
  function stop(){ seq += 1; left = 0; syn.cancel(); reset(); }
  function voice(){
    var vs = syn.getVoices().filter(function(v){ return (v.lang || "").toLowerCase().replace("_", "-").indexOf(lang) === 0; });
    var eg = vs.filter(function(v){ return /-eg$/i.test(v.lang.replace("_", "-")); });
    return eg[0] || vs.filter(function(v){ return v.localService; })[0] || vs[0] || null;
  }
  function sentences(body){                              // short pieces: some voices stop after a long one
    var out = [], els = body.querySelectorAll(":scope > p:not(.ex-say), li, dt, dd");
    for (var i = 0; i < els.length; i++){
      var t = els[i].textContent.replace(/\\s+/g, " ").trim();
      if (!t) continue;
      if (!/[.!?\\u061f:]$/.test(t)) t += ".";
      t.split(/(?<=[.!?\\u061f])\\s+/).forEach(function(s){ if (s) out.push(s); });
    }
    return out;
  }
  document.addEventListener("click", function(e){
    var b = e.target.closest && e.target.closest(".ex-body .speak");
    if (!b) return;
    if (on === b){ stop(); return; }
    stop();
    var note = b.parentNode.querySelector(".ex-note"), v = voice();
    if (!v && syn.getVoices().length){ note.textContent = b.getAttribute("data-none"); return; }
    note.textContent = "";
    var parts = sentences(b.closest(".ex-body")), run = seq;
    on = b; left = parts.length; b.textContent = b.getAttribute("data-stop"); b.setAttribute("aria-pressed", "true");
    parts.forEach(function(s){
      var u = new SpeechSynthesisUtterance(s);
      u.lang = v ? v.lang : (lang === "ar" ? "ar-EG" : "en-US");
      if (v) u.voice = v;
      u.rate = lang === "ar" ? 0.9 : 0.95;
      u.onend = function(){ if (run !== seq) return; left -= 1; if (left <= 0) reset(); };
      u.onerror = function(ev){                          // no voice for this language on this device: say so
        if (run !== seq) return;
        if (/unavailable/.test(ev.error || "")) note.textContent = b.getAttribute("data-none");
        left -= 1; if (left <= 0) reset();
      };
      syn.speak(u);
    });
  });
  document.addEventListener("toggle", function(e){
    var d = e.target;
    if (d.matches && d.matches("details.explain") && !d.open && on && d.contains(on)) stop();
  }, true);
  window.addEventListener("pagehide", function(){ syn.cancel(); });
})();"""


def inject(page: str, script: bool = True) -> str:
    """The bubbles' look before </head>, and the reader before </body> unless the page carries JS in its own script.
    The page's own CSP allows both inline."""
    page = page.replace("</head>", f'<style id="kb-explain">{CSS}</style></head>', 1)
    return page.replace("</body>", f"<script>{JS}</script></body>", 1) if script else page
