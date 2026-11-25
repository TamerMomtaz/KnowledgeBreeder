"""kb serve: your advice runs as pages on this machine, with Save buttons in place of commands to paste.

It listens on 127.0.0.1 only, so nothing on your network or the internet can reach it. To open it on your phone,
put Tailscale in front of it (``tailscale serve``): that shows it to your own devices on your tailnet and to nobody
else. Never put it behind a public tunnel (Tailscale Funnel, ngrok, a router port): the pages hold your private cards.

What it guards against, since a page in your own browser could try to talk to it:
- a request must name this machine (127.0.0.1, localhost) or your tailnet (a name ending in .ts.net) as its Host,
  which stops a web page from reaching it through a renamed address (DNS rebinding);
- a change must be a JSON POST carrying the header X-KB: 1, which a page from another site cannot send without
  asking first, and kb never says yes; an Origin header, when there is one, must be this same address;
- bodies are small (the inbox takes files up to 20 MB each), and every page says no to frames, referrers and
  outside resources.

Ratings, picks, lessons and the inbox go through the same code as the command line, so the rules are the same. What
you send to the inbox stays on this machine: see picture/inbox.py.
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import re
import sys
import threading
import time
import traceback
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from .. import explain, theme
from .. import where as wh
from ..runlog import RunLog, query
from . import actions, engines, icon, nudge, page, rating
from . import inbox as inb
from . import lessons as les
from . import private as prv
from . import soon as soon_mod

MAX_BODY = 64_000
MAX_INBOX_BODY = 30_000_000          # up to ten files a send, each up to inbox.MAX_FILE, sent as base64
MAX_CARDS_BODY = 4_000_000           # one cards file, as text
SHORT_NOTE = 280                     # words sent with files and no longer than this are their note, not a post
RUN = re.compile(r"^/run/(run_[0-9A-Za-z]{6,32})$")
CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: 'self'; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
LOCAL = {"127.0.0.1", "localhost", "[::1]"}

LABELS = {
    "en": {
        "title": "Your kb",
        "sub": "Served by kb on this laptop. Only this laptop, and your own devices through Tailscale, can open it.",
        "via": "Opened as {who} through your tailnet.",
        "runs_h": "Runs", "none": "No advice run yet. Press Ask for advice.",
        "rated": "rated {r} of {n}", "not_rated": "not rated yet", "picked": "picked {w}", "failed": "failed",
        "nobody": "no answer", "lessons_h": "Your lessons",
        "lessons_note": "Every advice run follows them. Add one in your own words; it counts from the next run.",
        "no_lessons": "No lessons yet.", "add": "Add lesson", "lesson_ph": "A rule for kb's advice, in your own words",
        "saving": "Saving…", "not_saved": "Not saved: {e}", "other": "العربية", "other_lang": "ar",
        "private": "Private: these pages hold lines from your cards. kb serve shows them only to you.",
        "inbox_h": "Your inbox",
        "inbox_note": "Paste a post or a link, attach screenshots, PDFs, Word files or voice notes, or record one. "
                      "It all stays on this laptop, and kb reads what it can here.",
        "inbox_ph": "Paste a post or a link, or write a few words. A few words sent with files become their note.",
        "attach": "Attach files", "record": "Record a voice note", "stop": "Stop recording",
        "send": "Send to kb", "sending": "Sending…", "sent": "Kept: {n}.", "again": "{n} already in your inbox.",
        "in_cards": "Cards files: {n}. They went into your picture, not the inbox; Ask kb says what changed.",
        "not_sent": "Not sent: {e}. Sending again is safe: kb keeps each thing once.",
        "remove": "Remove {name}", "too_big": "{name} is over 20 MB, so kb cannot keep it.",
        "no_mic": "No microphone: {e}", "inbox_empty": "Nothing here yet.",
        "inbox_more": "{n} items in all. On the laptop: kb inbox",
        "k_text": "text", "k_link": "link", "k_pdf": "PDF", "k_word": "Word", "k_slides": "slides",
        "k_image": "picture", "k_audio": "voice", "k_other": "file",
        "ask_h": "Ask kb",
        "ask_note": "Each button runs here on the laptop, with the models on this laptop only. You can leave the page "
                    "while kb works.",
        "ask_models": "Models on this laptop: {names}.", "ask_no_models": "No model on this laptop yet: {e}",
        "ask_cards": "Your picture: {n} cards.", "ask_no_picture": "No cards yet. Add a cards file here.",
        "b_advise": "Ask for advice", "b_scout": "Find chances in my inbox", "b_cards": "Add cards from a file",
        "l_check": "Check my picture", "l_chances": "See chances ({n} open)",
        "starting": "Starting…", "reading": "Reading the file…",
        "j_advise": "kb is asking {who} for advice. It can take a few minutes.",
        "j_scout": "kb is reading your inbox with {who}.",
        "j_advice_done": "Advice is ready from {who}.",
        "j_advice_some": "Advice is ready from {who}. No answer from {bad}: {e}",
        "j_advice_none": "No model gave advice. {bad}: {e}",
        "j_scout_done": "kb read your inbox. New: {n}. Chances: {c}. Not confirmed: {u}.",
        "j_scout_nothing": "Nothing new in your inbox to read.", "j_scout_old": "Read before: {n}.",
        "j_failed": "It did not work: {e}", "j_open_run": "Open the advice", "j_open_chances": "See chances",
        "busy": "kb is busy with another job. Wait for it to finish, then press again.",
        "no_inbox_text": "Your inbox has nothing kb can read yet. Send a post, a link or a file first.",
        "cards_done": "New cards: {a}. Updated: {u}. Unchanged: {s}. Cards in your picture now: {n}.",
        "cards_none": "No PROJECT CARD in {name}, so nothing was added.", "cards_changed": "What changed:",
        "cards_see": "See where your work waits",
        "check_title": "Is your picture ready?", "chances_title": "Chances from your inbox",
        "back": "Back to kb", "en_only": "This page is in English for now.",
        "no_chances_yet": "kb has not read your inbox yet. Press Find chances in my inbox on the first page.",
        "where_h": "Where you were",
        "where_note": "kb can show the pages you visited, what you searched and asked AI, and the files you opened or "
                      "changed. It reads them on this laptop each time, keeps none of it, and sends nothing anywhere.",
        "where_on": "Show where I was", "where_off": "Stop showing where I was",
        "where_sum": "{since}. AI chats: {ai}. Searches: {search}. Documents: {doc}. Files opened: {opened}. "
                     "Files changed: {changed}. Other pages: {web}.",
        "d_1": "Today", "d_2": "Since yesterday", "d_7": "Last 7 days", "d_30": "Last 30 days",
        "where_all": "See all and find a word", "where_find": "Find a word in where you were",
        "where_found": "Showing {n}.", "where_none": "Nothing for these days.",
        "where_partial": "Your home folder is big, so kb stopped looking for changed files after {s} seconds. "
                         "Some may be missing.",
        "where_problem": "Could not read {e}", "where_browsers": "Browsers read: {b}.",
        "where_no_browser": "kb found no browser history in your home folder.",
        "k_ai": "AI chat", "k_search": "search", "k_doc": "document", "k_web": "page", "k_opened": "opened",
        "k_changed": "changed",
        "s_ai": "AI chats", "s_search": "Searches", "s_doc": "Documents and research", "s_opened": "Files you opened",
        "s_changed": "Files you changed", "s_web": "Other pages",
        "keep": "Keep in inbox", "kept_one": "Kept in your inbox.", "today": "today", "yesterday": "yesterday",
        "files_n": "Files: {n}", "gone": "no longer there", "times": "opened {n} times",
        "shared": "Shared to kb. Add a few words if you like, then press Send to kb.",
        "share_again": "kb was not ready for that share. Open kb once on this phone, then share again.",
        "app_desc": "Your kb: send it posts, links, screenshots, files and voice notes from any app.",
        "soon_h": "Coming up",
        "soon_note": "Dates written on your cards and the deadlines of open chances, nearest first. kb guesses none of them.",
        "soon_missed": "Slipped, {when}, and still open", "soon_due": "Due {when}", "soon_on": "{when}",
        "soon_chance": "A chance from your inbox, closes {when}", "soon_who": "Waits on {who}.",
        "soon_you": "Waits on you.",
        "nudge_h": "Reminders on your phone",
        "nudge_note": "kb sends your phone a morning note (what is close, what slipped, what waits on you) and a reminder "
                      "the day before and on the day of each deadline. They go through ntfy, a free notification app. "
                      "Only short lines leave this laptop, and anything private is cut down to its card's name. ntfy "
                      "keeps each note on its server for up to 12 hours. The laptop must be on.",
        "nudge_on": "Turn on phone reminders", "nudge_off": "Turn off phone reminders", "nudge_test": "Send a test now",
        "nudge_s1": "Install the free ntfy app on your phone (Google Play, F-Droid or the App Store).",
        "nudge_s2": "Subscribe to your topic. On Android, open this page on the phone and press Subscribe on the phone. "
                    "On an iPhone, press + in the app and type the topic below.",
        "nudge_s3": "Press Send a test now. A note arrives in a few seconds.",
        "nudge_sub": "Subscribe on the phone",
        "nudge_topic": "Your topic. Keep it to yourself: anyone who has it can read the notes.",
        "nudge_when": "Morning note: once a day, between 8:00 and 14:00. Deadline reminders: the day before and on the "
                      "day, between 8:00 and 22:00. Nothing at night.",
        "nudge_last": "Last sent: {last}", "nudge_none": "Nothing sent yet.",
        "nudge_err": "The last try failed: {e}. kb tries again in five minutes.",
        "nudge_sent": "Sent. Look at your phone.", "nudge_first": "Turn phone reminders on first.",
        "eng_h": "Where your work waits",
        "eng_note": "Worked out from your cards on this laptop, with no model: what waits on whom, and how long things "
                    "wait. The math comes from your research Mathematical Engines of Plan→T.",
        "eng_frees": "What frees the most",
        "eng_you": "Needs that wait on you: {n} of {all}. On cards: {c}.",
        "eng_row": "{who}. Needs: {n}. Cards: {c}.",
        "eng_row_free": "Once done, nothing is left waiting on: {names}.",
        "eng_you_name": "You", "eng_nobody": "Nobody named", "eng_more": "And {n} more.",
        "eng_one": "One step from free: each of these cards waits on one thing only.",
        "eng_waits_on": "waits on {who}", "eng_you_in": "you", "eng_nobody_in": "nobody named",
        "eng_row_free_nobody": "Name who does these, and once they are done nothing is left waiting on: {names}.",
        "eng_wait": "How long things wait",
        "eng_open": "Open now. Needs not met: {n}. Open decisions: {d}. Unfinished pieces: {u}.",
        "eng_pace": "You close about {p} a week. At that pace a new one waits about {w} weeks.",
        "eng_none_closed": "Days of versions: {d}, and nothing closed in them. At this pace, what waits does not get done.",
        "eng_early": "Days kb has kept versions of your cards: {d}. After {m} it can tell your pace.",
        "eng_flow": "Since kb began keeping versions. Opened: {o}. Closed: {c}.",
        "eng_growing": "More open than close, so the wait keeps growing.",
        "eng_quiet": "Quiet longest",
        "eng_quiet_row": "Open: {n}. Days since it last moved: {d}.",
        "eng_no_waiting": "No card has a need waiting.",
        "eng_problem": "Could not read your cards: {e}",
    },
    "ar": {
        "title": "kb الخاص بك",
        "sub": "يعرضها kb من هذا اللابتوب. لا يفتحها إلا هذا اللابتوب وأجهزتك أنت عبر Tailscale.",
        "via": "فُتحت باسم {who} عبر شبكتك الخاصة.",
        "runs_h": "التشغيلات", "none": "لا يوجد تشغيل نصائح بعد. اضغط اطلب نصيحة.",
        "rated": "التقييم: {r} من {n}", "not_rated": "لم يُقيَّم بعد", "picked": "الاختيار: {w}", "failed": "فشل",
        "nobody": "لا إجابة", "lessons_h": "دروسك",
        "lessons_note": "كل تشغيل نصائح يتبعها. أضف درسًا بكلماتك، ويُحسب من التشغيل التالي.",
        "no_lessons": "لا دروس بعد.", "add": "أضف الدرس", "lesson_ph": "قاعدة لنصائح kb بكلماتك",
        "saving": "جارٍ الحفظ…", "not_saved": "لم يُحفظ: {e}", "other": "English", "other_lang": "en",
        "private": "خاص: هذه الصفحات تحمل سطورًا من بطاقاتك، ولا يعرضها kb serve إلا لك.",
        "inbox_h": "صندوقك",
        "inbox_note": "الصق منشورًا أو رابطًا، أو أرفق لقطات شاشة وملفات PDF وWord ورسائل صوتية، أو سجّل واحدة. "
                      "كل شيء يبقى على هذا اللابتوب، ويقرأ kb ما يستطيع هنا.",
        "inbox_ph": "الصق منشورًا أو رابطًا، أو اكتب كلمات قليلة. الكلمات القليلة المرسلة مع ملفات تصير ملاحظتها.",
        "attach": "أرفق ملفات", "record": "سجّل رسالة صوتية", "stop": "أوقف التسجيل",
        "send": "أرسل إلى kb", "sending": "جارٍ الإرسال…", "sent": "حُفظ: {n}.", "again": "موجود من قبل في صندوقك: {n}.",
        "in_cards": "ملفات بطاقات: {n}. ذهبت إلى صورتك لا إلى الصندوق، ويقول «اسأل kb» ما الذي تغيّر.",
        "not_sent": "لم يُرسل: {e}. الإرسال مرة أخرى آمن: يحفظ kb كل شيء مرة واحدة.",
        "remove": "احذف {name}", "too_big": "{name} أكبر من 20 ميغابايت، فلا يحفظه kb.",
        "no_mic": "لا ميكروفون: {e}", "inbox_empty": "لا شيء هنا بعد.",
        "inbox_more": "عدد العناصر كلها: {n}. على اللابتوب: kb inbox",
        "k_text": "نص", "k_link": "رابط", "k_pdf": "PDF", "k_word": "Word", "k_slides": "شرائح",
        "k_image": "صورة", "k_audio": "صوت", "k_other": "ملف",
        "ask_h": "اسأل kb",
        "ask_note": "كل زر يعمل هنا على اللابتوب، بنماذج هذا اللابتوب فقط. يمكنك ترك الصفحة أثناء عمل kb.",
        "ask_models": "النماذج على هذا اللابتوب: {names}.", "ask_no_models": "لا نموذج على هذا اللابتوب بعد: {e}",
        "ask_cards": "صورتك: {n} بطاقة.", "ask_no_picture": "لا بطاقات بعد. أضف ملف بطاقات من هنا.",
        "b_advise": "اطلب نصيحة", "b_scout": "ابحث عن فرص في صندوقي", "b_cards": "أضف بطاقات من ملف",
        "l_check": "افحص صورتي", "l_chances": "الفرص (المفتوحة: {n})",
        "starting": "جارٍ البدء…", "reading": "جارٍ قراءة الملف…",
        "j_advise": "يطلب kb النصيحة من {who}. قد يستغرق ذلك بضع دقائق.",
        "j_scout": "يقرأ kb صندوقك بواسطة {who}.",
        "j_advice_done": "النصيحة جاهزة من {who}.",
        "j_advice_some": "النصيحة جاهزة من {who}. لا إجابة من {bad}: {e}",
        "j_advice_none": "لم يقدّم أي نموذج نصيحة. {bad}: {e}",
        "j_scout_done": "قرأ kb صندوقك: الجديد {n}، والفرص {c}، وغير المؤكد {u}.",
        "j_scout_nothing": "لا جديد في صندوقك للقراءة.", "j_scout_old": "قُرئ من قبل: {n}.",
        "j_failed": "لم ينجح: {e}", "j_open_run": "افتح النصيحة", "j_open_chances": "اعرض الفرص",
        "busy": "kb مشغول بمهمة أخرى. انتظر حتى تنتهي، ثم اضغط مرة أخرى.",
        "no_inbox_text": "لا شيء في صندوقك يستطيع kb قراءته بعد. أرسل منشورًا أو رابطًا أو ملفًا أولًا.",
        "cards_done": "بطاقات جديدة: {a}. حُدّثت: {u}. بلا تغيير: {s}. في صورتك الآن: {n}.",
        "cards_none": "لا توجد PROJECT CARD في {name}، فلم يُضف شيء.", "cards_changed": "ما الذي تغيّر:",
        "cards_see": "انظر أين ينتظر عملك",
        "check_title": "هل صورتك جاهزة؟", "chances_title": "الفرص من صندوقك",
        "back": "عودة إلى kb", "en_only": "هذه الصفحة بالإنجليزية حاليًا.",
        "no_chances_yet": "لم يقرأ kb صندوقك بعد. اضغط «ابحث عن فرص في صندوقي» في الصفحة الأولى.",
        "where_h": "أين كنت",
        "where_note": "يستطيع kb أن يعرض الصفحات التي زرتها، وما بحثت عنه وسألت عنه الذكاء الاصطناعي، والملفات التي "
                      "فتحتها أو غيّرتها. يقرؤها من هذا اللابتوب في كل مرة، ولا يحتفظ بشيء منها، ولا يرسل شيئًا إلى أي مكان.",
        "where_on": "اعرض أين كنت", "where_off": "أوقف عرض أين كنت",
        "where_sum": "{since}. محادثات ذكاء اصطناعي: {ai}. عمليات بحث: {search}. مستندات: {doc}. ملفات فتحتها: "
                     "{opened}. ملفات غيّرتها: {changed}. صفحات أخرى: {web}.",
        "d_1": "اليوم", "d_2": "منذ أمس", "d_7": "آخر 7 أيام", "d_30": "آخر 30 يومًا",
        "where_all": "اعرض الكل وابحث عن كلمة", "where_find": "ابحث عن كلمة فيما زرته",
        "where_found": "المعروض: {n}.", "where_none": "لا شيء في هذه الأيام.",
        "where_partial": "مجلدك الرئيسي كبير، فتوقف kb عن البحث عن الملفات المتغيرة بعد {s} ثوانٍ. قد ينقص بعضها.",
        "where_problem": "تعذرت قراءة {e}", "where_browsers": "المتصفحات المقروءة: {b}.",
        "where_no_browser": "لم يجد kb سجل تصفح في مجلدك الرئيسي.",
        "k_ai": "ذكاء اصطناعي", "k_search": "بحث", "k_doc": "مستند", "k_web": "صفحة", "k_opened": "فُتح",
        "k_changed": "تغيّر",
        "s_ai": "محادثات الذكاء الاصطناعي", "s_search": "عمليات البحث", "s_doc": "المستندات والأبحاث",
        "s_opened": "ملفات فتحتها", "s_changed": "ملفات غيّرتها", "s_web": "صفحات أخرى",
        "keep": "احفظه في الصندوق", "kept_one": "حُفظ في صندوقك.", "today": "اليوم", "yesterday": "أمس",
        "files_n": "ملفات: {n}", "gone": "لم يعد موجودًا", "times": "مرات الفتح: {n}",
        "shared": "وصلت المشاركة إلى kb. أضف كلمات إن شئت، ثم اضغط أرسل إلى kb.",
        "share_again": "لم يكن kb جاهزًا لهذه المشاركة. افتح kb مرة على هذا الهاتف، ثم شارك مرة أخرى.",
        "app_desc": "kb الخاص بك: أرسل إليه المنشورات والروابط ولقطات الشاشة والملفات والرسائل الصوتية من أي تطبيق.",
        "soon_h": "قريبًا",
        "soon_note": "تواريخ مكتوبة على بطاقاتك ومواعيد الفرص المفتوحة، الأقرب أولًا. لا يخمّن kb أيًّا منها.",
        "soon_missed": "فات موعده {when} وما زال مفتوحًا", "soon_due": "موعده {when}", "soon_on": "{when}",
        "soon_chance": "فرصة من صندوقك، تُغلق {when}", "soon_who": "ينتظر: {who}.",
        "soon_you": "ينتظرك أنت.",
        "nudge_h": "تذكيرات على هاتفك",
        "nudge_note": "يرسل kb إلى هاتفك رسالة صباحية (ما اقترب، وما فات موعده، وما ينتظرك) وتذكيرًا قبل كل موعد نهائي "
                      "بيوم وفي يومه. تصل عبر ntfy، وهو تطبيق إشعارات مجاني. لا يخرج من هذا اللابتوب إلا سطور قصيرة، "
                      "وكل ما هو خاص يُختصر إلى اسم بطاقته. يحتفظ ntfy بكل رسالة على خادمه حتى 12 ساعة. يجب أن يكون "
                      "اللابتوب يعمل.",
        "nudge_on": "شغّل تذكيرات الهاتف", "nudge_off": "أوقف تذكيرات الهاتف", "nudge_test": "أرسل تجربة الآن",
        "nudge_s1": "ثبّت تطبيق ntfy المجاني على هاتفك (\u2068Google Play\u2069 أو \u2068F-Droid\u2069 أو \u2068App Store\u2069).",
        "nudge_s2": "اشترك في موضوعك. على أندرويد، افتح هذه الصفحة على الهاتف واضغط «اشترك على الهاتف». على آيفون، "
                    "اضغط + في التطبيق واكتب الموضوع أدناه.",
        "nudge_s3": "اضغط «أرسل تجربة الآن». تصل رسالة خلال ثوانٍ.",
        "nudge_sub": "اشترك على الهاتف",
        "nudge_topic": "موضوعك. احتفظ به لنفسك: من يعرفه يستطيع قراءة الرسائل.",
        "nudge_when": "الرسالة الصباحية: مرة في اليوم بين 8:00 و14:00. تذكيرات المواعيد: قبل الموعد بيوم وفي يومه، بين "
                      "8:00 و22:00. لا شيء ليلًا.",
        "nudge_last": "آخر إرسال: {last}", "nudge_none": "لم يُرسل شيء بعد.",
        "nudge_err": "فشلت المحاولة الأخيرة: {e}. يحاول kb مرة أخرى بعد خمس دقائق.",
        "nudge_sent": "أُرسلت. انظر إلى هاتفك.", "nudge_first": "شغّل تذكيرات الهاتف أولًا.",
        "eng_h": "أين ينتظر عملك",
        "eng_note": "محسوب من بطاقاتك على هذا اللابتوب، دون أي نموذج: ما ينتظر مَن، وكم تنتظر الأشياء. الحساب مأخوذ من "
                    "بحثك Mathematical Engines of Plan→T.",
        "eng_frees": "ما الذي يحرّر أكثر",
        "eng_you": "احتياجات تنتظرك: {n} من {all}. على بطاقات عددها: {c}.",
        "eng_row": "{who}. احتياجات: {n}. بطاقات: {c}.",
        "eng_row_free": "بعد إنجازه لا يبقى شيء ينتظر في: {names}.",
        "eng_you_name": "أنت", "eng_nobody": "لم يُسمَّ أحد", "eng_more": "وغيرها: {n}.",
        "eng_one": "على بُعد خطوة: كل بطاقة من هذه تنتظر شيئًا واحدًا فقط.",
        "eng_waits_on": "تنتظر: {who}", "eng_you_in": "أنت", "eng_nobody_in": "لم يُسمَّ أحد",
        "eng_row_free_nobody": "سمِّ مَن يقوم بها، وبعد إنجازها لا يبقى شيء ينتظر في: {names}.",
        "eng_wait": "كم تنتظر الأشياء",
        "eng_open": "المفتوح الآن. احتياجات لم تتحقق: {n}. قرارات مفتوحة: {d}. أعمال غير مكتملة: {u}.",
        "eng_pace": "تُغلق في الأسبوع نحو: {p}. بهذه الوتيرة ينتظر الجديد بالأسابيع نحو: {w}.",
        "eng_none_closed": "أيام النسخ: {d}، ولم يُغلق فيها شيء. بهذه الوتيرة لا يُنجَز ما ينتظر.",
        "eng_early": "أيام احتفاظ kb بنسخ بطاقاتك: {d}. بعد {m} يومًا يستطيع أن يقرأ وتيرتك.",
        "eng_flow": "منذ بدأ kb يحتفظ بالنسخ. فُتح: {o}. أُغلق: {c}.",
        "eng_growing": "ما يُفتح أكثر مما يُغلق، فالانتظار يطول باستمرار.",
        "eng_quiet": "الأطول هدوءًا",
        "eng_quiet_row": "مفتوح: {n}. أيام منذ آخر حركة: {d}.",
        "eng_no_waiting": "لا توجد بطاقة فيها احتياج ينتظر.",
        "eng_problem": "تعذرت قراءة بطاقاتك: {e}",
    },
}


def _t(lang: str, key: str, **v) -> str:
    s = LABELS[lang][key]
    for k, x in v.items():
        s = s.replace("{" + k + "}", f"\u2068{x}\u2069" if lang == "ar" else str(x))
    return s


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def host_ok(host: str | None, port: int) -> bool:
    """This machine by name or number, on our port, or a name on your tailnet (tailscale serve keeps the Host)."""
    if not host:
        return False
    host = host.strip().lower()
    name, _, p = host.rpartition(":") if not host.endswith("]") else (host, "", "")
    if not name:                        # no port given
        name, p = host, ""
    if name in LOCAL:
        return p == str(port)
    return name.endswith(".ts.net") and p in ("", "443")


def _changes(raw) -> list[tuple[int, str, bool]]:
    """Your changes to pieces as the page sends them: [{"n": 2, "text": "...", "lesson": true}, ...]."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 50:
        raise KeyError("changes must be a short list.")
    out = []
    for c in raw:
        if not (isinstance(c, dict) and isinstance(c.get("n"), int) and not isinstance(c.get("n"), bool)
                and isinstance(c.get("text"), str) and isinstance(c.get("lesson", False), bool)):
            raise KeyError("each change needs a piece number n, its text, and lesson true or false.")
        out.append((c["n"], c["text"], c.get("lesson", False)))
    return out


def verdicts(log: RunLog) -> dict[str, dict]:
    """For each advice run: how many models answered, how many answers you rated, and whom you picked."""
    out: dict[str, dict] = {}
    for r in log.db.execute("""
            SELECT s.run_id, s.id, s.worker,
                   EXISTS(SELECT 1 FROM scores c WHERE c.step_id = s.id AND c.name = 'would_act') AS rated,
                   (SELECT c.value FROM scores c WHERE c.step_id = s.id AND c.name = 'picked' ORDER BY c.id DESC LIMIT 1) AS picked
            FROM steps s JOIN runs r ON r.id = s.run_id
            WHERE r.task = 'advise' AND s.name = 'advise' AND s.status = 'ok' AND s.worker IS NOT NULL"""):
        x = out.setdefault(r["run_id"], {"answers": 0, "rated": 0, "picked": None})
        x["answers"] += 1
        x["rated"] += r["rated"]
        if r["picked"] == 1.0:
            x["picked"] = r["worker"]
    return out


INDEX_CSS = """
:root{--bg:#f4f1ea;--ink:#1d2430;--soft:#5b6472;--line:#d9d3c6;--card:#fffdf8;--accent:#0b6bcb;--warn:#b45309;--ok:#15803d}
@media (prefers-color-scheme: dark){:root{--bg:#10151d;--ink:#e8ecf2;--soft:#9aa6b6;--line:#2a3340;--card:#171e29;--accent:#6cb6ff;--warn:#fbbf24;--ok:#4ade80}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans","Noto Naskh Arabic","Geeza Pro",Tahoma,sans-serif}
button,textarea{font:inherit;color:inherit}
.wrap{max-width:1240px;margin:0 auto;padding:20px 16px 40px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:26px;align-items:start}
@media (max-width:900px){.layout{grid-template-columns:minmax(0,1fr);gap:0}}
h1{font-size:clamp(1.5rem,5vw,2rem);line-height:1.15;margin:0 0 4px}
h2{font-size:1.15rem;margin:0 0 8px}
p{margin:0 0 6px}
.soft{color:var(--soft)}
.small{font-size:.9rem}
.top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.top a{color:var(--accent);white-space:nowrap}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:0 0 22px}
.runs{list-style:none;margin:0;padding:0}
.runs li{border-top:1px solid var(--line)}
.runs li:first-child{border-top:0}
.runs a{display:flex;flex-wrap:wrap;gap:2px 12px;align-items:baseline;padding:12px 4px;min-height:48px;color:inherit;text-decoration:none}
.runs a:hover .who,.runs a:focus-visible .who{text-decoration:underline}
.date{font-weight:600}
.who{color:var(--accent);font-weight:600}
.state{color:var(--soft);font-size:.92rem;margin-inline-start:auto}
.state.todo{color:var(--warn);font-weight:600}
.state.done{color:var(--ok)}
.lessons{margin:8px 0 12px;padding-inline-start:22px}
.lessons li{margin:0 0 4px}
textarea{width:100%;min-height:84px;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px;resize:vertical}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px}
button{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:0 18px;min-height:44px;cursor:pointer;font-weight:600}
@media (prefers-color-scheme: dark){button{color:#06121f}}
button:disabled{opacity:.6;cursor:default}
.err{color:var(--warn)}
.btn{background:var(--card);color:var(--ink);border:1.5px solid var(--line)}
.pending{list-style:none;margin:6px 0 0;padding:0}
.pending li{display:flex;gap:10px;align-items:center;justify-content:space-between;border-top:1px dashed var(--line);padding:4px 0}
.pending span{overflow-wrap:anywhere}
.pending .btn{min-height:40px;min-width:44px;padding:0 12px;font-size:1.1rem}
.inbox{list-style:none;margin:14px 0 0;padding:0}
.inbox li{display:grid;grid-template-columns:4.6em minmax(0,1fr);column-gap:10px;row-gap:2px;border-top:1px solid var(--line);padding:10px 2px}
.kind{grid-row:1/span 4;font-weight:700}
.what{grid-column:2;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;line-clamp:3;overflow:hidden}
.inbox .note{grid-column:2;font-size:.92rem;border-inline-start:3px solid var(--line);padding-inline-start:8px;margin:2px 0}
.meta{grid-column:2;display:flex;flex-wrap:wrap;gap:0 14px;color:var(--soft);font-size:.88rem}
.kept{color:var(--ok);font-weight:600}
.drop{outline:2px dashed var(--accent);outline-offset:4px}
footer{color:var(--soft);font-size:.86rem;margin-top:20px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.acts{display:flex;flex-direction:column;align-items:stretch;gap:12px;margin:12px 0 4px}
.acts button{width:100%}
.ask p{overflow-wrap:anywhere}
.nudge .topic code{display:block;overflow-wrap:anywhere;user-select:all;font-size:.95rem}
.nudge .steps{padding-inline-start:22px}
.nudge .steps li{margin:0 0 6px}
.links{display:flex;flex-wrap:wrap;gap:0 18px;margin-top:8px}
.links a{color:var(--accent);font-weight:600;min-height:44px;display:inline-flex;align-items:center}
#job{margin:10px 0 0;min-height:1.5em;overflow-wrap:anywhere}
#job a{color:var(--accent);font-weight:600}
#job .changed{display:block;color:var(--soft);font-size:.9rem;margin-top:4px}
ol.md,ul.md{margin:6px 0 4px;padding-inline-start:24px}
ol.md li,ul.md li{margin:0 0 12px;overflow-wrap:anywhere}
.more{display:block;color:var(--soft);font-size:.92rem;margin-top:3px}
.doc .box p{overflow-wrap:anywhere}
.doc .wrap{max-width:900px}
.trail{list-style:none;margin:10px 0 0;padding:0}
.trail li{display:grid;grid-template-columns:7.4em minmax(0,1fr) auto;column-gap:12px;border-top:1px solid var(--line);padding:9px 2px;align-items:center}
.trail li:first-child{border-top:0}
.trail .t{color:var(--soft);font-size:.86rem;grid-row:1/span 2;align-self:start;padding-top:2px}
.trail .ti{grid-column:2;overflow-wrap:anywhere;font-weight:600;color:inherit}
.trail a.ti{color:var(--accent)}
.trail .h{grid-column:2;color:var(--soft);font-size:.86rem;overflow-wrap:anywhere;display:flex;flex-wrap:wrap;gap:0 10px}
.trail .k{font-weight:700;color:var(--ink)}
.trail .keep{grid-column:3;grid-row:1/span 2;min-height:40px;padding:0 12px;font-size:.88rem}
.trail .keep.kept{color:var(--ok)}
.trail .fold{display:block}
.trail .fold>details>summary{cursor:pointer;min-height:44px;display:flex;flex-wrap:wrap;align-items:center;gap:0 12px;overflow-wrap:anywhere}
.trail .fold ul{padding-inline-start:10px}
@media (max-width:600px){.trail li{grid-template-columns:minmax(0,1fr) auto}.trail .t{grid-row:auto;grid-column:1}
  .trail .ti,.trail .h{grid-column:1}.trail .keep{grid-column:2;grid-row:1/span 3}}
.days{display:flex;flex-wrap:wrap;gap:0 18px;margin:4px 0 10px}
.days a{color:var(--accent);min-height:44px;display:inline-flex;align-items:center}
.days a[aria-current]{color:var(--ink);font-weight:700;text-decoration:none}
.eng h3{font-size:1.02rem;margin:16px 0 4px}
.soon li.missed .when{color:var(--warn);font-weight:700}
.soon li.deadline .when{font-weight:700}
.soon .c{display:block;font-weight:700}
.eng .lead{font-weight:700}
input[type=search]{width:100%;min-height:46px;background:var(--bg);color:inherit;border:1px solid var(--line);border-radius:10px;padding:0 12px;font:inherit}
"""

INDEX_JS = """
(function(){
"use strict";
var L = JSON.parse(document.getElementById("data").textContent);
if ("serviceWorker" in navigator && window.isSecureContext){ navigator.serviceWorker.register("/sw.js").catch(function(){}); }
var b = document.getElementById("add"), t = document.getElementById("lesson"), say = document.getElementById("say");
function ready(){ b.disabled = !t.value.trim(); }
t.addEventListener("input", ready); ready();
b.addEventListener("click", function(){
  b.disabled = true; b.textContent = L.saving; say.textContent = ""; say.className = "";
  fetch("/api/lesson", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"},
                        body: JSON.stringify({text: t.value})})
    .then(function(r){ return r.json().then(function(j){ return {ok: r.ok, j: j}; }); })
    .then(function(x){ if (!x.ok) throw new Error(x.j.error || "?"); location.reload(); })
    .catch(function(e){ b.textContent = L.add; ready(); say.textContent = L.not_saved.replace("{e}", e.message); say.className = "err"; });
});

var ask = document.getElementById("ask");
if (ask){
  var jobLine = document.getElementById("job"), acts = ask.querySelectorAll("button[data-job]"),
      cpick = document.getElementById("cards-pick"), cbtn = document.getElementById("cards");
  var jobLock = function(on){
    for (var i = 0; i < acts.length; i++) acts[i].disabled = on || acts[i].hasAttribute("data-off");
    cbtn.disabled = on;
  };
  var jobShow = function(j){
    jobLine.textContent = j.say || ""; jobLine.className = j.cls || "";
    if (j.link){ var a = document.createElement("a"); a.href = j.link; a.textContent = j.link_text;
      jobLine.appendChild(document.createTextNode(" ")); jobLine.appendChild(a); }
    (j.changed || []).forEach(function(c){ var s = document.createElement("span"); s.className = "changed";
      s.textContent = c; jobLine.appendChild(s); });
  };
  var jobCall = function(path, body){
    return fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify(body)})
      .then(function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.say || j.error || String(r.status)); return j; }); });
  };
  var redraw = function(){        // load the page again at the Ask box; a change of the #part alone would not reload it
    var u = "/?lang=" + L.lang;
    if (location.pathname + location.search === u){ history.replaceState(null, "", u + "#ask"); location.reload(); }
    else location.replace(u + "#ask");
  };
  var jobPoll = function(){
    fetch("/api/job?lang=" + L.lang).then(function(r){ return r.json(); }).then(function(j){
      jobShow(j);
      if (j.status === "running") setTimeout(jobPoll, 2500);
      else redraw();                                         // the new run, chances and counts show; the sentence stays
    }).catch(function(){ setTimeout(jobPoll, 5000); });
  };
  Array.prototype.forEach.call(acts, function(b){
    b.addEventListener("click", function(){
      jobLock(true); jobShow({say: L.starting});
      jobCall("/api/" + b.getAttribute("data-job"), {lang: L.lang}).then(function(j){ jobShow(j); jobPoll(); })
        .catch(function(e){ jobShow({say: e.message, cls: "err"}); jobLock(false); });
    });
  });
  cbtn.addEventListener("click", function(){ cpick.click(); });
  cpick.addEventListener("change", function(){
    var f = cpick.files && cpick.files[0]; cpick.value = "";
    if (!f) return;
    jobLock(true); jobShow({say: L.reading});
    var r = new FileReader();
    r.onload = function(){
      jobCall("/api/cards", {name: f.name, text: String(r.result), lang: L.lang})
        .then(function(j){
          jobShow(j);
          if (j.reload) redraw();                            // every box shows the new cards; the sentence stays
          else jobLock(false);
        })
        .catch(function(e){ jobShow({say: e.message, cls: "err"}); jobLock(false); });
    };
    r.onerror = function(){ jobShow({say: String(r.error || "?"), cls: "err"}); jobLock(false); };
    r.readAsText(f);
  });
  if (ask.getAttribute("data-running") === "1"){ jobLock(true); jobPoll(); }
}

function again(part){             // load the page again at a box; a change of the #part alone would not reload it
  var u = "/?lang=" + L.lang;
  if (location.pathname + location.search === u){ history.replaceState(null, "", u + part); location.reload(); }
  else location.replace(u + part);
}
var won = document.getElementById("where-on");
if (won){
  won.addEventListener("click", function(){
    won.disabled = true; won.textContent = L.saving;
    fetch("/api/where", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify({on: true})})
      .then(function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.error || "?"); again("#where"); }); })
      .catch(function(e){ won.disabled = false; won.textContent = L.where_on;
        var ws = document.getElementById("where-say"); ws.textContent = L.not_saved.replace("{e}", e.message); ws.className = "err"; });
  });
}

var nsay = document.getElementById("nudge-say");
function nudgeDo(b, what){
  var was = b.textContent;
  b.disabled = true; b.textContent = what === "test" ? L.sending : L.saving;
  fetch("/api/nudge", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify({do: what, lang: L.lang})})
    .then(function(r){ return r.json().then(function(j){
      if (!r.ok) throw new Error(j.error || "?");
      if (what !== "test") return again("#nudge");
      b.disabled = false; b.textContent = was; nsay.textContent = j.say; nsay.className = "kept";
    }); })
    .catch(function(e){ b.disabled = false; b.textContent = was; nsay.textContent = e.message; nsay.className = "err"; });
}
[["nudge-on", "on"], ["nudge-off", "off"], ["nudge-test", "test"]].forEach(function(p){
  var b = document.getElementById(p[0]);
  if (b) b.addEventListener("click", function(){ nudgeDo(b, p[1]); });
});

var post = document.getElementById("post");
if (!post) return;
var box = document.getElementById("inbox"), pick = document.getElementById("pick"), attach = document.getElementById("attach"),
    rec = document.getElementById("rec"), send = document.getElementById("send"), said = document.getElementById("said"),
    list = document.getElementById("pending"), files = [], busy = false, recording = false;
function two(n){ return ("0" + n).slice(-2); }
function stamp(){ var d = new Date(); return d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate()) + "-" + two(d.getHours()) + two(d.getMinutes()); }
function size(n){ return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
function tell(m, c){ said.textContent = m; said.className = c || ""; }
function can(){ send.disabled = busy || recording || (!post.value.trim() && !files.length); }
function draw(){
  list.textContent = "";
  files.forEach(function(f, i){
    var li = document.createElement("li"), s = document.createElement("span"), x = document.createElement("button");
    s.textContent = f.name + " (" + size(f.blob.size) + ")";
    x.type = "button"; x.className = "btn"; x.textContent = "\\u00d7"; x.setAttribute("aria-label", L.remove.replace("{name}", f.name));
    x.addEventListener("click", function(){ files.splice(i, 1); draw(); });
    li.appendChild(s); li.appendChild(x); list.appendChild(li);
  });
  can();
}
function take(fl){
  for (var i = 0; i < fl.length; i++){
    var f = fl[i];
    if (f.size > L.max_file){ tell(L.too_big.replace("{name}", f.name), "err"); continue; }
    files.push({name: f.name || "pasted-" + stamp(), blob: f});
  }
  draw();
}
post.addEventListener("input", can);
var asked = new URLSearchParams(location.search).get("shared");
if (asked === "again") tell(L.share_again, "err");
if (asked === "1" && window.caches){
  // the share helper (sw.js) kept what another app shared; put it in the box, and you press Send to kb
  caches.open("kb-share").then(function(c){
    return c.match("/share/meta").then(function(m){
      if (!m) return null;
      return m.json().then(function(meta){
        var words = [];
        [meta.title, meta.text, meta.url].forEach(function(w){
          w = (w || "").trim(); if (w && !words.some(function(o){ return o.indexOf(w) >= 0; })) words.push(w); });
        post.value = words.join("\\n");
        return Promise.all((meta.files || []).map(function(f, i){
          return c.match("/share/file/" + i).then(function(r){ return r ? r.blob() : null; }); }))
          .then(function(blobs){ blobs.forEach(function(x, i){ if (x){ x.name = meta.files[i].name; take([x]); } }); });
      });
    }).then(function(){ return caches.delete("kb-share"); });
  }).then(function(){ can(); tell(L.shared, "kept"); history.replaceState(null, "", "/?lang=" + L.lang + "#inbox"); post.focus(); })
    .catch(function(e){ tell(L.not_sent.replace("{e}", e.message), "err"); });
}
attach.addEventListener("click", function(){ pick.click(); });
pick.addEventListener("change", function(){ take(pick.files); pick.value = ""; });
post.addEventListener("paste", function(e){
  var c = e.clipboardData;
  if (c && c.files && c.files.length){ take(c.files); if (!(c.getData("text") || "").trim()) e.preventDefault(); }
});
box.addEventListener("dragover", function(e){ e.preventDefault(); box.classList.add("drop"); });
box.addEventListener("dragleave", function(){ box.classList.remove("drop"); });
box.addEventListener("drop", function(e){ e.preventDefault(); box.classList.remove("drop"); if (e.dataTransfer) take(e.dataTransfer.files); });

var mr = null, chunks = [], t0 = 0, tick = null;
rec.addEventListener("click", function(){
  if (recording){ mr.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder){ tell(L.no_mic.replace("{e}", "this browser cannot record"), "err"); return; }
  navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream){
    var type = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"].filter(function(x){
      return MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(x); })[0];
    chunks = [];
    mr = type ? new MediaRecorder(stream, {mimeType: type}) : new MediaRecorder(stream);
    mr.ondataavailable = function(e){ if (e.data && e.data.size) chunks.push(e.data); };
    mr.onstop = function(){
      clearInterval(tick); recording = false; rec.setAttribute("aria-pressed", "false"); rec.textContent = L.record;
      stream.getTracks().forEach(function(k){ k.stop(); });
      var mt = mr.mimeType || type || "audio/webm", blob = new Blob(chunks, {type: mt});
      var ext = mt.indexOf("mp4") >= 0 ? ".m4a" : mt.indexOf("ogg") >= 0 ? ".ogg" : ".webm";
      if (blob.size){ blob.name = "voice-note-" + stamp() + ext; take([blob]); } else { can(); }
    };
    mr.start(1000); recording = true; t0 = Date.now(); rec.setAttribute("aria-pressed", "true");
    var show = function(){ var s = Math.floor((Date.now() - t0) / 1000);
      rec.textContent = L.stop + " " + Math.floor(s / 60) + ":" + two(s % 60); if (s >= 900) mr.stop(); };
    show(); tick = setInterval(show, 1000); can();
  }).catch(function(e){ tell(L.no_mic.replace("{e}", e.message || e.name), "err"); });
});

function b64(blob){ return new Promise(function(ok, no){ var r = new FileReader();
  r.onload = function(){ var s = String(r.result); ok(s.slice(s.indexOf(",") + 1)); };
  r.onerror = function(){ no(r.error || new Error("could not read the file")); }; r.readAsDataURL(blob); }); }
function one(body){
  return fetch("/api/inbox", {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.error || String(r.status)); return j; }); });
}
send.addEventListener("click", function(){
  var text = post.value.trim(), jobs = [], note = "", kept = 0, again = 0, cards = 0, done = 0;
  if (text && (!files.length || text.length > L.short || /^https?:\\/\\/\\S+$/i.test(text))) jobs.push(function(){ return one({text: text}); });
  else note = text;
  files.forEach(function(f){ jobs.push(function(){ return b64(f.blob).then(function(d){ return one({name: f.name, data: d, note: note}); }); }); });
  busy = true; can(); send.textContent = L.sending; tell("");
  jobs.reduce(function(p, job){ return p.then(function(){ return job().then(function(j){
      if (j.kind === "cards") cards++; else if (j.new) kept++; else again++; done++; tell(done + " / " + jobs.length); }); }); }, Promise.resolve())
    .then(function(){ location.replace("/?lang=" + L.lang + "&kept=" + kept + "&again=" + again + "&cards=" + cards + "#inbox"); })
    .catch(function(e){ busy = false; send.textContent = L.send; can(); tell(L.not_sent.replace("{e}", e.message), "err"); });
});
})();
"""


def inbox_html(box: list[dict], lang: str, got: dict | None = None, show: int = 12) -> str:
    """The inbox box: paste, attach, record, send, then the newest items."""
    got = got or {}
    said = " ".join(x for x in (_t(lang, "sent", n=got["kept"]) if got.get("kept") else "",
                                _t(lang, "again", n=got["again"]) if got.get("again") else "",
                                _t(lang, "in_cards", n=got["cards"]) if got.get("cards") else "") if x)
    rows = []
    for x in box[:show]:
        what = x.get("name") or x.get("preview") or "-"
        notes = "".join(f'<span class="note"><bdi>{_e(n["text"][:200])}</bdi></span>' for n in x.get("notes", [])[-2:])
        rows.append(f'<li><span class="kind">{_e(_t(lang, "k_" + x["kind"]))}</span><span class="what"><bdi>{_e(what)}</bdi></span>'
                    f'{notes}<span class="meta"><span>{_e(x["received"])}</span><span>{_e(inb.say(x, lang))}</span></span></li>')
    items = (f'<ul class="inbox">{"".join(rows)}</ul>' + (f'<p class="soft small">{_e(_t(lang, "inbox_more", n=len(box)))}</p>'
             if len(box) > show else "")) if rows else f'<p class="soft small">{_e(_t(lang, "inbox_empty"))}</p>'
    return (f'<section class="box" id="inbox"><h2>{_e(_t(lang, "inbox_h"))} ({len(box)})</h2>'
            f'<p class="soft small">{_e(_t(lang, "inbox_note"))}</p>'
            + (f'<p class="kept" role="status">{_e(said)}</p>' if said else "") +
            f'<textarea id="post" dir="auto" placeholder="{_e(_t(lang, "inbox_ph"))}" aria-label="{_e(_t(lang, "inbox_ph"))}"></textarea>'
            f'<input type="file" id="pick" multiple hidden>'
            f'<div class="row"><button type="button" class="btn" id="attach">{_e(_t(lang, "attach"))}</button>'
            f'<button type="button" class="btn" id="rec" aria-pressed="false">{_e(_t(lang, "record"))}</button></div>'
            f'<ul class="pending" id="pending" aria-live="polite"></ul>'
            f'<div class="row"><button type="button" id="send" disabled>{_e(_t(lang, "send"))}</button>'
            f'<span id="said" role="status"></span></div>{items}</section>')


def job_say(state: dict, lang: str) -> dict:
    """What the page says about the job running now or the last one, as one plain sentence and maybe a link."""
    st, kind = state.get("status", "idle"), state.get("kind")
    out = {"status": st, "kind": kind, "say": "", "cls": ""}
    if st == "running":
        out["say"] = _t(lang, "j_advise" if kind == "advise" else "j_scout", who=", ".join(state.get("models") or []))
    elif st == "failed":
        out.update(say=_t(lang, "j_failed", e=state.get("error") or "?"), cls="err")
    elif st == "done" and kind == "advise":
        a = actions.advice_summary(state.get("result") or {})
        bad = ", ".join(x["worker"] for x in a["failed"])
        e = a["failed"][0]["error"] if a["failed"] else ""
        if a["ok"]:
            key = "j_advice_some" if a["failed"] else "j_advice_done"
            out.update(say=_t(lang, key, who=", ".join(a["ok"]), bad=bad, e=e), cls="kept")
            if a["run"]:
                out.update(link=f"/run/{a['run']}?lang={lang}", link_text=_t(lang, "j_open_run"))
        else:
            out.update(say=_t(lang, "j_advice_none", bad=bad or "-", e=e or "?"), cls="err")
    elif st == "done" and kind == "scout":
        c = actions.scout_summary(state.get("result") or {})
        say = _t(lang, "j_scout_done", n=c["read"], c=c["chances"], u=c["unsure"]) if c["read"] else _t(lang, "j_scout_nothing")
        if c["before"]:
            say += " " + _t(lang, "j_scout_old", n=c["before"])
        out.update(say=say, cls="kept", link=f"/chances?lang={lang}", link_text=_t(lang, "j_open_chances"))
    return out


def cards_say(r: dict, lang: str) -> dict:
    if not r["found"]:
        return {"say": _t(lang, "cards_none", name=r.get("name") or "-"), "cls": "err", **r}
    say = _t(lang, "cards_done", a=len(r["added"]), u=len(r["updated"]), s=len(r["unchanged"]), n=r["cards"])
    changed = [f"{name}: {line}" for name, line in r["changed"].items()]
    # new or changed cards change every count on the page, so the page loads again and this sentence stays on it
    return {**r, "say": say, "cls": "kept", "changed": ([_t(lang, "cards_changed")] + changed) if changed else [],
            "link": "#waits", "link_text": _t(lang, "cards_see"), "reload": bool(r["added"] or r["updated"])}


def ask_html(lang: str, cards: int | None, names: list[str], problem: str | None, job: dict, open_chances: int,
             cards_said: tuple[float, dict] | None = None) -> str:
    """The Ask kb box: the jobs that needed a terminal, as buttons, and what the last one said."""
    off = "" if names and cards else " data-off disabled"
    facts = [_t(lang, "ask_cards", n=cards) if cards else _t(lang, "ask_no_picture"),
             _t(lang, "ask_models", names=", ".join(names)) if names else _t(lang, "ask_no_models", e=problem or "?")]
    said = job_say(job, lang)
    if cards_said and job.get("status") != "running" and cards_said[0] >= (job.get("ended") or job.get("started") or 0):
        said = cards_say(cards_said[1], lang)                 # the cards file came after the last job
    link = (f' <a href="{_e(said["link"])}">{_e(said["link_text"])}</a>' if said.get("link") else "")
    running = job.get("status") == "running"
    return (f'<section class="box ask" id="ask" data-running="{1 if running else 0}"><h2>{_e(_t(lang, "ask_h"))}</h2>'
            f'<p class="soft small">{_e(_t(lang, "ask_note"))}</p>'
            + "".join(f'<p class="small"><bdi>{_e(x)}</bdi></p>' for x in facts) +
            f'<div class="acts"><button type="button" class="act" id="advise" data-job="advise"{off}>{_e(_t(lang, "b_advise"))}</button>'
            f'<button type="button" class="act" id="scout" data-job="scout"{" data-off disabled" if not names or not cards else ""}>'
            f'{_e(_t(lang, "b_scout"))}</button>'
            f'<button type="button" class="act alt" id="cards">{_e(_t(lang, "b_cards"))}</button></div>'
            f'<input type="file" id="cards-pick" accept=".md,.txt,text/markdown,text/plain" hidden>'
            f'<p id="job" role="status" class="{_e(said["cls"])}">{_e(said["say"])}{link}'
            + "".join(f'<span class="changed"><bdi>{_e(x)}</bdi></span>' for x in said.get("changed") or []) + '</p>'
            f'<div class="links"><a href="/check?lang={lang}">{_e(_t(lang, "l_check"))}</a>'
            f'<a href="/chances?lang={lang}">{_e(_t(lang, "l_chances", n=open_chances))}</a></div></section>')


def doc_page(lang: str, title: str, body: str, note: str | None = None) -> str:
    """A plain page for what kb used to print in the terminal: the check, the chances."""
    lang = lang if lang in LABELS else "en"
    other = LABELS[lang]["other_lang"]
    notes = f'<p class="soft small">{_e(note)}</p>' if note else ""
    return theme.inject(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">'
            f'<title>{_e(title)}</title><style>{INDEX_CSS}</style></head><body class="doc"><div class="wrap">'
            f'<header><div class="top"><h1>{_e(title)}</h1><a href="?lang={other}" lang="{other}">{_e(LABELS[lang]["other"])}</a></div>'
            f'<p><a href="/?lang={lang}">{_e(_t(lang, "back"))}</a></p>{notes}</header>'
            f'<main lang="en" dir="ltr">{body}</main>'
            f'<footer><p>{_e(_t(lang, "private"))}</p></footer></div></body></html>')


WHERE_TOP = ("ai", "search", "doc", "opened")
WHERE_DAYS = (1, 2, 7, 30)
WHERE_CAP = 1000                     # lines a section shows; a word you search for finds older ones

WHERE_JS = """
(function(){
"use strict";
var L = JSON.parse(document.getElementById("data").textContent);
var f = document.getElementById("find"), n = document.getElementById("found");
function post(path, body){
  return fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-KB": "1"}, body: JSON.stringify(body)})
    .then(function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.say || j.error || String(r.status)); return j; }); });
}
function run(){
  var ws = f.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
  Array.prototype.forEach.call(document.querySelectorAll("li[data-text]"), function(li){
    var t = li.getAttribute("data-text"), ok = ws.every(function(w){ return t.indexOf(w) >= 0; });
    li.hidden = !ok; if (ok) shown++;
  });
  Array.prototype.forEach.call(document.querySelectorAll("li.fold"), function(li){
    li.hidden = !li.querySelector("li[data-text]:not([hidden])");
    if (ws.length && !li.hidden) li.querySelector("details").open = true;
  });
  Array.prototype.forEach.call(document.querySelectorAll("section[data-kind]"), function(sc){
    sc.hidden = !sc.querySelector("li[data-text]:not([hidden])");
  });
  n.textContent = L.where_found.replace("{n}", shown);
}
if (f){
  f.addEventListener("input", run);
  f.addEventListener("keydown", function(e){
    if (e.key === "Enter"){ e.preventDefault();
      location.href = "/where?days=" + L.days + "&lang=" + L.lang + "&q=" + encodeURIComponent(f.value.trim()); }
  });
  run();
}
document.addEventListener("click", function(e){
  var b = e.target.closest ? e.target.closest("button.keep") : null;
  if (!b || b.disabled) return;
  b.disabled = true;
  var body = b.hasAttribute("data-path") ? {path: b.getAttribute("data-path"), lang: L.lang}
                                         : {url: b.getAttribute("data-url"), title: b.getAttribute("data-title"), lang: L.lang};
  post("/api/where/keep", body).then(function(j){ b.textContent = j.say; b.classList.add("kept"); })
    .catch(function(x){ b.disabled = false; b.textContent = x.message; b.classList.add("err"); });
});
var off = document.getElementById("where-off");
if (off) off.addEventListener("click", function(){
  off.disabled = true;
  post("/api/where", {on: false}).then(function(){ location.replace("/?lang=" + L.lang); })
    .catch(function(x){ off.disabled = false; off.textContent = x.message; });
});
})();
"""


def _when(ts: float, now: float, lang: str) -> str:
    return wh.when(ts, now, (_t(lang, "today"), _t(lang, "yesterday")))


def where_line(x: dict, data: dict, lang: str, keep: bool = False) -> str:
    """One page or file: when, what, where, and a button to keep it in the inbox."""
    k = x["kind"]
    text = _e(f'{x["title"]} {x["where"]}'.lower())
    notes = []
    if k in ("opened", "changed"):
        title = f'<bdi class="ti">{_e(x["title"])}</bdi>'
        place = _e(wh.short(x["where"], data["home"]))
        btn = (f'<button type="button" class="btn keep" data-path="{_e(x["where"])}">{_e(_t(lang, "keep"))}</button>'
               if keep and not x.get("gone") else "")
        if x.get("gone"):
            notes.append(_t(lang, "gone"))
    else:
        title = (f'<a class="ti" href="{_e(x["where"])}" target="_blank" rel="noreferrer noopener">'
                 f'<bdi>{_e(x["title"])}</bdi></a>')
        place = _e(wh.host(x["where"]))
        btn = (f'<button type="button" class="btn keep" data-url="{_e(x["where"])}" data-title="{_e(x["title"][:300])}">'
               f'{_e(_t(lang, "keep"))}</button>' if keep else "")
    if x.get("count", 1) > 1 and k != "changed":
        notes.append(_t(lang, "times", n=x["count"]))
    extra = "".join(f"<span>{_e(n)}</span>" for n in notes)
    return (f'<li data-text="{text}"><span class="t">{_e(_when(x["ts"], data["now"], lang))}</span>{title}'
            f'<span class="h"><span class="k">{_e(_t(lang, "k_" + k))}</span><bdi dir="ltr">{place}</bdi>{extra}</span>'
            f'{btn}</li>')


def _where_notes(data: dict, lang: str) -> str:
    out = []
    if data["browsers"]:
        out.append(_t(lang, "where_browsers", b=", ".join(data["browsers"])))
    else:
        out.append(_t(lang, "where_no_browser"))
    out += [_t(lang, "where_problem", e=p) for p in data["problems"]]
    if data["stopped"]:
        out.append(_t(lang, "where_partial", s=f'{data["budget"]:g}'))
    return "".join(f'<p class="soft small"><bdi>{_e(x)}</bdi></p>' for x in out)


def where_box(lang: str, on: bool, data: dict | None, problem: str | None = None) -> str:
    """The Where you were box on the first page: off until you turn it on, then the newest pages and files."""
    head = f'<section class="box where" id="where"><h2>{_e(_t(lang, "where_h"))}</h2>'
    if not on:
        return (head + f'<p class="soft small">{_e(_t(lang, "where_note"))}</p><div class="row">'
                f'<button type="button" class="act alt" id="where-on">{_e(_t(lang, "where_on"))}</button>'
                f'<span id="where-say" role="status"></span></div></section>')
    if data is None:
        return head + f'<p class="err">{_e(_t(lang, "where_problem", e=problem or "?"))}</p></section>'
    c = wh.counts(data["items"])
    summary = _t(lang, "where_sum", since=_t(lang, f'd_{data["days"]}'), **c)
    top = [x for x in data["items"] if x["kind"] in WHERE_TOP][:8]
    lst = (f'<ul class="trail">{"".join(where_line(x, data, lang) for x in top)}</ul>' if top
           else f'<p class="soft">{_e(_t(lang, "where_none"))}</p>')
    return (head + f'<p><bdi>{_e(summary)}</bdi></p>{lst}{_where_notes(data, lang)}'
            f'<div class="links"><a href="/where?lang={lang}">{_e(_t(lang, "where_all"))}</a></div></section>')


def soon_box(lang: str, rows: list[dict], show: int = 8) -> str:
    """Coming up, first on the page: what slipped and what is close. Nothing when no date is close."""
    if not rows:
        return ""
    out = []
    for x in rows[:show]:
        d = date.fromisoformat(x["when"])
        day = (f'{d.day}/{d.month}' if lang == "ar" else f'{d:%a} {d.day} {d:%b}')
        when = soon_mod.when_words(x["days"], lang)
        head = {"missed": "soon_missed", "deadline": "soon_due", "date": "soon_on", "chance": "soon_chance"}[x["kind"]]
        who, m = "", engines.YOU.match(x["who"] or "")
        if m and not x["who"][m.end():].strip():
            who = _e(_t(lang, "soon_you"))
        elif x["who"]:                                    # the name isolated, so Arabic and English sit right
            name = "you" + x["who"][m.end():] if m and lang == "en" else x["who"]
            pre, post = LABELS[lang]["soon_who"].split("{who}")
            who = f'{_e(pre)}<bdi>{_e(name)}</bdi>{_e(post)}'
        card = f'<span class="c"><bdi>{_e(x["card"])}</bdi></span>' if x["card"] else ""
        out.append(f'<li class="{_e(x["kind"])}">{card}<bdi>{_e(x["what"])}</bdi>'
                   f'<span class="more"><span class="when">{_e(_t(lang, head, when=when))} · {_e(day)}</span>'
                   f'{(" " + who) if who else ""}</span></li>')
    return (f'<section class="box soon" id="soon"><h2>{_e(_t(lang, "soon_h"))}</h2>'
            f'<p class="soft small">{_e(_t(lang, "soon_note"))}</p><ul class="md">{"".join(out)}</ul></section>')


def nudge_box(lang: str, s: dict) -> str:
    """Reminders on your phone: off until you press the button, then the steps for the phone and a test button."""
    head = (f'<section class="box nudge" id="nudge"><h2>{_e(_t(lang, "nudge_h"))}</h2>'
            f'<p class="soft small">{_e(_t(lang, "nudge_note"))}</p>')
    say = '<span id="nudge-say" role="status"></span>'
    if not s.get("on") or not s.get("topic"):
        return (head + f'<div class="row"><button type="button" class="act alt" id="nudge-on">'
                f'{_e(_t(lang, "nudge_on"))}</button>{say}</div></section>')
    host = urlsplit(s["server"]).netloc or "ntfy.sh"
    sub = f'ntfy://{host}/{s["topic"]}?display=kb'
    steps = (f'<ol class="md steps"><li>{_e(_t(lang, "nudge_s1"))}</li>'
             f'<li>{_e(_t(lang, "nudge_s2"))} <a href="{_e(sub)}">{_e(_t(lang, "nudge_sub"))}</a></li>'
             f'<li>{_e(_t(lang, "nudge_s3"))}</li></ol>')
    topic = (f'<p class="soft small">{_e(_t(lang, "nudge_topic"))}</p>'
             f'<p class="topic"><code dir="ltr">{_e(s["topic"])}</code></p>')
    if s.get("error"):
        state = f'<p class="err small"><bdi>{_e(_t(lang, "nudge_err", e=s["error"]))}</bdi></p>'
    elif s.get("last"):
        state = f'<p class="soft small"><bdi>{_e(_t(lang, "nudge_last", last=s["last"]))}</bdi></p>'
    else:
        state = f'<p class="soft small">{_e(_t(lang, "nudge_none"))}</p>'
    return (head + steps + topic + f'<p class="soft small">{_e(_t(lang, "nudge_when"))}</p>' + state +
            f'<div class="acts"><button type="button" class="act" id="nudge-test">{_e(_t(lang, "nudge_test"))}</button>'
            f'<button type="button" class="act alt" id="nudge-off">{_e(_t(lang, "nudge_off"))}</button></div>'
            f'<div class="row">{say}</div></section>')


def waits_box(lang: str, r: dict | None, problem: str | None = None) -> str:
    """Where your work waits: what frees the most, and how long things wait. Worked out from the cards, no model."""
    head = (f'<section class="box eng" id="waits"><h2>{_e(_t(lang, "eng_h"))}</h2>'
            f'<p class="soft small">{_e(_t(lang, "eng_note"))}</p>')
    if r is None:
        return head + f'<p class="err">{_e(_t(lang, "eng_problem", e=problem or "?"))}</p></section>'
    f, c = r["frees"], r["clock"]

    def who(x: dict, inside: bool = False) -> str:
        if x["you"]:
            return _t(lang, "eng_you_in" if inside else "eng_you_name")
        return x["who"] or _t(lang, "eng_nobody_in" if inside else "eng_nobody")

    out = [head, f'<h3>{_e(_t(lang, "eng_frees"))}</h3>']
    if not f["waiting"]:
        out.append(f'<p>{_e(_t(lang, "eng_no_waiting"))}</p>')
    else:
        if f["you"]:
            out.append(f'<p class="lead">{_e(_t(lang, "eng_you", n=f["you"]["needs"], all=f["waiting"], c=f["you"]["cards"]))}</p>')
        rows = []
        for g in f["by"]:
            say = "eng_row_free_nobody" if g["nobody"] else "eng_row_free"
            free = (f'<span class="more">{_e(_t(lang, say, names=", ".join(g["free"])))}</span>'
                    if g["free"] else "")
            rows.append(f'<li>{_e(_t(lang, "eng_row", who=who(g), n=g["needs"], c=g["cards"]))}{free}</li>')
        if f["more"]:
            rows.append(f'<li class="soft">{_e(_t(lang, "eng_more", n=f["more"]))}</li>')
        out.append(f'<ul class="md">{"".join(rows)}</ul>')
        if f["one_step"]:
            out.append(f'<p>{_e(_t(lang, "eng_one"))}</p><ul class="md">' + "".join(
                f'<li><b><bdi>{_e(x["card"])}</bdi></b>: <bdi>{_e(x["need"])}</bdi>'
                f'<span class="more">{_e(_t(lang, "eng_waits_on", who=who(x, True)))}</span></li>' for x in f["one_step"])
                + "</ul>")
    o = c["open"]
    out.append(f'<h3>{_e(_t(lang, "eng_wait"))}</h3>'
               f'<p>{_e(_t(lang, "eng_open", n=o["needs"], d=o["decisions"], u=o["unfinished"]))}</p>'
               f'<p>{_e(engines.pace(c, lang))}</p>')
    if c["ready"] and (c["opened"] or c["closed"]):
        grow = f' <b>{_e(_t(lang, "eng_growing"))}</b>' if c["growing"] else ""
        out.append(f'<p>{_e(_t(lang, "eng_flow", o=c["opened"], c=c["closed"]))}{grow}</p>')
    if c["quiet"]:
        out.append(f'<h3>{_e(_t(lang, "eng_quiet"))}</h3><ul class="md">' + "".join(
            f'<li><bdi>{_e(x["card"])}</bdi><span class="more">{_e(_t(lang, "eng_quiet_row", n=x["open"], d=x["days"]))}'
            f'</span></li>' for x in c["quiet"]) + "</ul>")
    return "".join(out) + "</section>"


def where_page(lang: str, data: dict, q: str = "") -> str:
    """Everything kb can see of where you were, by kind, with a word filter and a Keep button on each line."""
    lang = lang if lang in LABELS else "en"
    other = LABELS[lang]["other_lang"]
    items = wh.find(data["items"], q) if q else data["items"]
    here = ' aria-current="page"'
    days = "".join(f'<a href="/where?days={d}&amp;lang={lang}"{here if d == data["days"] else ""}>'
                   f'{_e(_t(lang, "d_" + str(d)))}</a>' for d in WHERE_DAYS)
    secs = []
    for k in ("ai", "search", "doc", "opened", "changed", "web"):
        rows = [x for x in items if x["kind"] == k]
        if not rows:
            continue
        if k == "changed":
            lis = []
            for g in wh.folders(rows)[:WHERE_CAP]:
                files = "".join(where_line(x, data, lang, keep=True) for x in g["files"][:200])
                lis.append(f'<li class="fold"><details><summary><span class="t">{_e(_when(g["ts"], data["now"], lang))}</span>'
                           f'<bdi dir="ltr" class="ti">{_e(wh.short(g["folder"], data["home"]))}</bdi>'
                           f'<span class="soft small">{_e(_t(lang, "files_n", n=len(g["files"])))}</span></summary>'
                           f'<ul class="trail">{files}</ul></details></li>')
            body = "".join(lis)
        else:
            body = "".join(where_line(x, data, lang, keep=True) for x in rows[:WHERE_CAP])
        more = (f'<p class="soft small">{_e(_t(lang, "where_found", n=f"{WHERE_CAP} / {len(rows)}"))}</p>'
                if len(rows) > WHERE_CAP and k != "changed" else "")
        secs.append(f'<section class="box" data-kind="{k}"><h2>{_e(_t(lang, "s_" + k))} ({len(rows)})</h2>'
                    f'<ul class="trail">{body}</ul>{more}</section>')
    c = wh.counts(items)
    summary = _t(lang, "where_sum", since=_t(lang, f'd_{data["days"]}'), **c)
    main = "".join(secs) or f'<section class="box"><p>{_e(_t(lang, "where_none"))}</p></section>'
    blob = json.dumps({"lang": lang, "days": data["days"], "where_found": LABELS[lang]["where_found"]},
                      ensure_ascii=False).replace("<", "\\u003c")
    title = _t(lang, "where_h")
    return theme.inject(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">'
            f'<title>{_e(title)}</title><style>{INDEX_CSS}</style></head><body class="doc"><div class="wrap">'
            f'<header><div class="top"><h1>{_e(title)}</h1><a href="/where?days={data["days"]}&amp;lang={other}" lang="{other}">'
            f'{_e(LABELS[lang]["other"])}</a></div>'
            f'<p><a href="/?lang={lang}">{_e(_t(lang, "back"))}</a></p><nav class="days">{days}</nav>'
            f'<p><bdi>{_e(summary)}</bdi></p>'
            f'<input type="search" id="find" dir="auto" value="{_e(q)}" placeholder="{_e(_t(lang, "where_find"))}" '
            f'aria-label="{_e(_t(lang, "where_find"))}"><p class="soft small" id="found" role="status"></p>'
            f'{_where_notes(data, lang)}</header><main>{main}</main>'
            f'<footer><p>{_e(_t(lang, "where_note"))}</p><div class="row"><button type="button" class="btn" id="where-off">'
            f'{_e(_t(lang, "where_off"))}</button></div></footer></div>'
            f'<script id="data" type="application/json">{blob}</script><script>{WHERE_JS}</script></body></html>')


# The share helper. A phone that has kb on its home screen lists kb in its Share menu; what you share arrives here as
# a form, and this keeps it in the phone's own cache and opens kb's page with it in the inbox box. Nothing is sent to
# the laptop until you press Send to kb, through the same /api/inbox as the page.
SW_JS = """
"use strict";
self.addEventListener("install", function(){ self.skipWaiting(); });
self.addEventListener("activate", function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function(e){
  var u = new URL(e.request.url);
  if (e.request.method !== "POST" || u.origin !== self.location.origin || u.pathname !== "/share") return;
  e.respondWith((async function(){
    var f = await e.request.formData();
    var files = f.getAll("files").filter(function(x){ return x && typeof x === "object" && x.size > 0; });
    await caches.delete("kb-share");
    var c = await caches.open("kb-share");
    for (var i = 0; i < files.length; i++){
      await c.put("/share/file/" + i, new Response(files[i], {headers: {"Content-Type": files[i].type || "application/octet-stream"}}));
    }
    await c.put("/share/meta", new Response(JSON.stringify({title: f.get("title") || "", text: f.get("text") || "",
      url: f.get("url") || "", files: files.map(function(x){ return {name: x.name || "shared", type: x.type || ""}; })}),
      {headers: {"Content-Type": "application/json"}}));
    return Response.redirect("/?shared=1#inbox", 303);
  })());
});
"""

SHARE_ACCEPT = ["image/*", "audio/*", "video/*", "text/*", "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".pdf", ".docx", ".pptx", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp", ".m4a", ".ogg", ".opus", ".mp3"]


def manifest(lang: str) -> dict:
    """What a phone needs to put kb on its home screen and in its Share menu."""
    return {"name": "kb", "short_name": "kb", "id": "/", "description": _t(lang, "app_desc"),
            "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "start_url": "/", "scope": "/",
            "display": "standalone", "background_color": "#10151d", "theme_color": "#1d2430",
            "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
            "share_target": {"action": "/share", "method": "POST", "enctype": "multipart/form-data",
                             "params": {"title": "title", "text": "text", "url": "url",
                                        "files": [{"name": "files", "accept": SHARE_ACCEPT}]}}}


def index(log: RunLog | None, lessons: list[str], lang: str = "en", who: str | None = None, limit: int = 60,
          today: date | None = None, box: list[dict] | None = None, got: dict | None = None,
          ask: str | None = None, where: str | None = None, waits: str | None = None, soon: str | None = None,
          nudges: str | None = None) -> str:
    """The first page: your inbox, every advice run, newest first, with what you have recorded, and your lessons."""
    lang = lang if lang in LABELS else "en"
    runs = query.runs(log, task="advise", limit=limit) if log else []
    seen = verdicts(log) if log else {}
    items = []
    for r in runs:
        v = seen.get(r["id"], {"answers": 0, "rated": 0, "picked": None})
        if r["status"] == "failed" and not v["answers"]:
            state, cls = _t(lang, "failed"), "state"
        elif not v["answers"]:
            state, cls = _t(lang, "nobody"), "state"
        elif v["rated"] < v["answers"]:
            state, cls = _t(lang, "rated", r=v["rated"], n=v["answers"]) if v["rated"] else _t(lang, "not_rated"), "state todo"
        else:
            state, cls = _t(lang, "rated", r=v["rated"], n=v["answers"]), "state done"
        if v["picked"]:
            state += " · " + _t(lang, "picked", w=v["picked"])
        items.append(f'<li><a href="/run/{_e(r["id"])}?lang={lang}"><span class="date">{_e(r["started"][:10])}</span>'
                     f'<span class="who"><bdi>{_e(", ".join((r["label"] or "-").split(",")))}</bdi></span><span class="{cls}">{_e(state)}</span></a></li>')
    runs_html = f'<ul class="runs">{"".join(items)}</ul>' if items else f'<p class="soft">{_e(_t(lang, "none"))}</p>'
    lesson_html = ('<ol class="lessons">' + "".join(f'<li><bdi>{_e(x)}</bdi></li>' for x in lessons) + "</ol>"
                   if lessons else f'<p class="soft">{_e(_t(lang, "no_lessons"))}</p>')
    via = f'<p class="soft small">{_e(_t(lang, "via", who=who))}</p>' if who else ""
    hud = theme.hud(theme.standing(page.history(log, limit=1_000_000) if log else [], today), lang)
    keys = ("add", "saving", "not_saved", "send", "sending", "not_sent", "record", "stop", "remove", "too_big", "no_mic",
            "starting", "reading", "where_on", "shared", "share_again")
    runs_box = f'<section class="box" id="runs"><h2>{_e(_t(lang, "runs_h"))}</h2>{runs_html}</section>'
    lessons_box = (f'<section class="box" id="lessons"><h2>{_e(_t(lang, "lessons_h"))} ({len(lessons)})</h2>'
                   f'<p class="soft small">{_e(_t(lang, "lessons_note"))}</p>{lesson_html}'
                   f'<textarea id="lesson" dir="auto" maxlength="600" placeholder="{_e(_t(lang, "lesson_ph"))}" '
                   f'aria-label="{_e(_t(lang, "lesson_ph"))}"></textarea>'
                   f'<div class="row"><button type="button" id="add">{_e(_t(lang, "add"))}</button>'
                   f'<span id="say" role="status"></span></div></section>')
    # Wide like the advice page: the inbox takes the wide column, runs and lessons the narrow one. On a phone it is one
    # column, inbox first. Without an inbox the runs take the wide column.
    # The Ask kb box comes first in the narrow column: the buttons for what used to need the terminal.
    if box is not None:
        main = (soon or "") + inbox_html(box, lang, got) + (waits or "") + (where or "")
        side = (ask or "") + (nudges or "") + runs_box + lessons_box
    else:
        main, side = (soon or "") + runs_box + (waits or "") + (where or ""), (ask or "") + (nudges or "") + lessons_box
    blob = json.dumps({**{k: LABELS[lang][k] for k in keys}, "lang": lang, "short": SHORT_NOTE, "max_file": inb.MAX_FILE},
                      ensure_ascii=False).replace("<", "\\u003c")
    doc = (f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">'
            f'<title>{_e(_t(lang, "title"))}</title><link rel="manifest" href="/manifest.webmanifest">'
            f'<link rel="icon" href="/icon-192.png" sizes="192x192"><meta name="theme-color" content="#1d2430">'
            f'<style>{INDEX_CSS}</style></head><body><div class="wrap">'
            f'<header><div class="top"><h1>{_e(_t(lang, "title"))}</h1><a href="/?lang={LABELS[lang]["other_lang"]}" '
            f'lang="{LABELS[lang]["other_lang"]}">{_e(LABELS[lang]["other"])}</a></div>'
            f'<p class="soft">{_e(_t(lang, "sub"))}</p>{via}{explain.guide(lang)}{hud}</header>'
            f'<div class="layout"><div class="main">{main}</div><div class="side">{side}</div></div>'
            f'<footer><p>{_e(_t(lang, "private"))}</p></footer></div>'
            f'<script id="data" type="application/json">{blob}</script><script>{INDEX_JS}\n{explain.JS}</script></body></html>')
    # a ? on every box, with the buttons named as the page names them (without a count in brackets)
    def name(k: str) -> str:
        return re.sub(r"\s*\(.*$", "", LABELS[lang][k])
    return explain.inject(theme.inject(explain.add(doc, lang, name)), script=False)


class Kb:
    """What the server needs: where your files are, and its own port. Whatever is not named sits beside the lessons
    file (work/ by default): picture.json, models.json, private.md, scout.jsonl, cards/ and inbox/. Paths are kept
    whole, so the buttons work whichever folder kb serve was started from."""

    def __init__(self, runlog: str | Path, lessons: str | Path, port: int, lang: str = "en", today: date | None = None,
                 inbox: str | Path | None = None, picture: str | Path | None = None, models: str | Path | None = None,
                 private: str | Path | None = None, ledger: str | Path | None = None, cards: str | Path | None = None,
                 jobs: actions.Jobs | None = None, home: str | Path | None = None, where_budget: float = 4.0):
        self.runlog, self.lessons, self.port, self.lang, self.today = (Path(runlog).absolute(), Path(lessons).absolute(),
                                                                       port, lang, today)
        work = self.lessons.parent
        self.inbox = inb.Inbox(Path(inbox).absolute() if inbox is not None else work / "inbox")
        self.picture = Path(picture).absolute() if picture else work / "picture.json"
        self.models = Path(models).absolute() if models else work / "models.json"
        self.private = Path(private).absolute() if private else work / "private.md"
        self.ledger = Path(ledger).absolute() if ledger else work / "scout.jsonl"
        self.cards = Path(cards).absolute() if cards else work / "cards"
        self.jobs = jobs or actions.Jobs()
        self.where_file = work / "where.json"
        self.home, self.where_budget = (Path(home) if home else None), where_budget
        self._where: dict[int, tuple[float, dict]] = {}
        self._where_lock = threading.Lock()
        self.where_paths: set[str] = set()
        self._waits: tuple | None = None
        self.cards_said: tuple[float, dict] | None = None     # when the page last added a cards file, and what it found
        self.nudge = nudge.Nudge(work / "nudge.json")
        self.nudge_post = nudge._post                           # tests put a stand-in here; nothing leaves then
        self.nudge_lock = threading.Lock()

    def log(self) -> RunLog | None:
        return RunLog(self.runlog) if self.runlog.exists() else None

    def cards_count(self) -> int | None:
        if not self.picture.exists():
            return None
        from . import Picture
        try:
            return len(Picture.load(self.picture).cards)
        except (ValueError, KeyError, OSError):
            return None

    def open_chances(self) -> int:
        if not self.ledger.exists():
            return 0
        from .. import scout
        return len(scout.open_now(scout.Ledger(self.ledger).rows(), self.today))

    def ask(self, lang: str) -> str:
        names, problem = actions.here_models(self.models)
        return ask_html(lang, self.cards_count(), names, problem, self.jobs.state(), self.open_chances(),
                        self.cards_said)

    def where_on(self) -> bool:
        try:
            return json.loads(self.where_file.read_text(encoding="utf-8")).get("on") is True
        except (OSError, ValueError, AttributeError):
            return False

    def set_where(self, on: bool) -> None:
        self.where_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.where_file.with_suffix(".part")
        tmp.write_text(json.dumps({"on": bool(on), "since": (self.today or date.today()).isoformat()}), encoding="utf-8")
        tmp.replace(self.where_file)
        self._where.clear()

    def where(self, days: int = 2, fresh: float = 120) -> dict:
        """What kb can see of where you were, read again at most every two minutes."""
        with self._where_lock:
            hit = self._where.get(days)
            if hit and time.monotonic() - hit[0] < fresh:
                return hit[1]
            data = wh.gather(days, self.home, skip=[self.lessons.parent], budget=self.where_budget)
            self._where[days] = (time.monotonic(), data)
            self.where_paths |= {x["where"] for x in data["items"] if x["kind"] in ("opened", "changed")}
            return data

    def waits(self) -> dict | None:
        """The two engines on the cards, worked out again only when the picture file or the day changes."""
        if not self.picture.exists():
            return None
        today = self.today or date.today()
        key = (self.picture.stat().st_mtime_ns, today)
        if self._waits and self._waits[0] == key:
            return self._waits[1]
        from . import Picture
        r = engines.run(Picture.load(self.picture), today)
        self._waits = (key, r)
        return r

    def soon(self, today: date | None = None) -> list[dict]:
        """Coming up: dates on the cards and deadlines of open chances. Empty while there is no picture."""
        from . import Picture
        if not self.picture.exists():
            return []
        today = today or self.today or date.today()
        chances = []
        if self.ledger.exists():
            from .. import scout
            chances = scout.open_now(scout.Ledger(self.ledger).rows(), today)
        return soon_mod.coming(Picture.load(self.picture).cards, today, chances)

    def soon_html(self, lang: str) -> str:
        try:
            rows = self.soon()
        except (ValueError, KeyError, OSError):
            traceback.print_exc()
            return ""
        return soon_box(lang, rows)

    def nudge_html(self, lang: str) -> str:
        return nudge_box(lang, self.nudge.state())

    def nudge_guard(self) -> prv.Private:
        """Your private list, with the names of cards marked #private, as the advice page uses it."""
        from . import Picture
        from .advise import guard_for
        g = prv.Private.load(self.private)
        return guard_for(Picture.load(self.picture), g) if self.picture.exists() else g

    def nudge_tick(self, now: datetime | None = None) -> list[str]:
        """Send what is due now, once. Nothing happens while reminders are off."""
        with self.nudge_lock:
            if not self.nudge.state()["on"]:
                return []
            try:
                waits = self.waits()
            except (ValueError, KeyError, OSError):
                waits = None
            now = now or datetime.now()
            return self.nudge.tick(now, self.soon(now.date()), waits, self.nudge_guard(), post=self.nudge_post)

    def start_nudges(self, every: float = 300) -> threading.Thread:
        """Check every five minutes, while kb serve runs, whether a reminder is due."""
        def loop():
            while True:
                try:
                    self.nudge_tick()
                except Exception:                     # noqa: BLE001 - a reminder that fails must not stop the page
                    traceback.print_exc()
                time.sleep(every)
        t = threading.Thread(target=loop, name="kb-nudge", daemon=True)
        t.start()
        return t

    def waits_html(self, lang: str) -> str:
        """The box, or nothing while there are no cards: the Ask kb box already says how to add them."""
        try:
            r = self.waits()
        except (ValueError, KeyError, OSError) as e:
            return waits_box(lang, None, f"{type(e).__name__}: {e}")
        return waits_box(lang, r) if r is not None else ""

    def where_html(self, lang: str) -> str:
        if not self.where_on():
            return where_box(lang, False, None)
        try:
            return where_box(lang, True, self.where(2))
        except Exception as e:                            # noqa: BLE001 - the rest of the page must still open
            traceback.print_exc()
            return where_box(lang, True, None, f"{type(e).__name__}: {e}")


class Handler(BaseHTTPRequestHandler):
    kb: Kb
    server_version = "kb"
    sys_version = ""

    def log_message(self, fmt, *args):                    # one quiet line per request, no addresses or bodies
        path = urlsplit(self.path).path
        if path != "/api/job":                            # the page asks every few seconds while a job runs
            sys.stderr.write(f"  {self.command} {path} {args[1] if len(args) > 1 else ''}\n")

    def _send(self, code: int, body: str | bytes, kind: str = "text/html; charset=utf-8") -> None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _redirect(self, to: str) -> None:
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _lang(self) -> str:
        lang = (parse_qs(urlsplit(self.path).query).get("lang") or [self.kb.lang])[0]
        return lang if lang in LABELS else self.kb.lang

    def _guard(self) -> bool:
        if not host_ok(self.headers.get("Host"), self.kb.port):
            self._send(421, "kb serve answers only to this machine and to your own tailnet name (ending in .ts.net).",
                       "text/plain; charset=utf-8")
            return False
        return True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard():
            return
        path, lang = urlsplit(self.path).path, self._lang()
        try:
            if path == "/":
                self._remember_page()
                log = self.kb.log()
                try:
                    q = parse_qs(urlsplit(self.path).query)
                    got = {k: int(v[0]) for k, v in q.items() if k in ("kept", "again", "cards") and v and v[0].isdigit()}
                    body = index(log, les.read(self.kb.lessons), lang, self.headers.get("Tailscale-User-Login"),
                                 today=self.kb.today, box=self.kb.inbox.items(), got=got, ask=self.kb.ask(lang),
                                 where=self.kb.where_html(lang), waits=self.kb.waits_html(lang),
                                 soon=self.kb.soon_html(lang), nudges=self.kb.nudge_html(lang))
                finally:
                    if log:
                        log.close()
                return self._send(200, body)
            m = RUN.match(path)
            if m:
                log = self.kb.log()
                if not log:
                    return self._send(404, "No run log yet.", "text/plain; charset=utf-8")
                try:
                    run_id = log.get(m.group(1)).id
                    data = page.gather(log, run_id)
                    hist = page.history(log)
                    record = theme.standing(page.history(log, limit=1_000_000), self.kb.today)
                finally:
                    log.close()
                return self._send(200, page.build(data, hist, lang=lang, today=self.kb.today, live=True, record=record))
            if path == "/api/job":
                return self._json(200, job_say(self.kb.jobs.state(), lang))
            if path == "/check":
                return self._send(200, self._check(lang))
            if path == "/chances":
                return self._send(200, self._chances(lang))
            if path == "/where":
                if not self.kb.where_on():
                    return self._redirect(f"/?lang={lang}#where")
                q = parse_qs(urlsplit(self.path).query)
                days = int((q.get("days") or ["2"])[0]) if (q.get("days") or ["2"])[0].isdigit() else 2
                days = days if days in WHERE_DAYS else 2
                return self._send(200, where_page(lang, self.kb.where(days), (q.get("q") or [""])[0][:200]))
            if path == "/manifest.webmanifest":
                return self._send(200, json.dumps(manifest(self.kb.lang), ensure_ascii=False),
                                  "application/manifest+json; charset=utf-8")
            if path == "/sw.js":
                return self._send(200, SW_JS, "text/javascript; charset=utf-8")
            if path in ("/icon-192.png", "/icon-512.png"):
                return self._send(200, icon.png(192 if "192" in path else 512), "image/png")
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return None
            return self._send(404, "Not here. Your runs are at /", "text/plain; charset=utf-8")
        except KeyError as e:
            return self._send(404, str(e.args[0]), "text/plain; charset=utf-8")
        except Exception as e:                                # noqa: BLE001 - say what broke, keep serving
            traceback.print_exc()
            return self._send(500, f"kb hit an error: {type(e).__name__}: {e}", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._guard():
            return None
        path = urlsplit(self.path).path
        if path == "/share":
            # a share the helper did not catch (kb not opened on this phone yet). Nothing in it is read or kept, so no
            # other site can put anything in your inbox this way; the page asks you to share again.
            return self._redirect("/?shared=again#inbox")
        if self.headers.get("X-KB") != "1":
            return self._json(403, {"error": "kb takes changes only from its own pages."})
        origin = urlsplit(self.headers.get("Origin") or "").netloc.lower()
        if origin and origin != (self.headers.get("Host") or "").lower() and not host_ok(origin, self.kb.port):
            # a proxy may pass the Host on or rewrite it to 127.0.0.1; either way the page must come from here
            return self._json(403, {"error": "kb takes changes only from its own pages."})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "send JSON."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        cap = MAX_INBOX_BODY if path == "/api/inbox" else MAX_CARDS_BODY if path == "/api/cards" else MAX_BODY
        if n < 0 or n > cap:
            return self._json(413, {"error": f"too long; kb takes up to {cap:,} bytes here."})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self._json(400, {"error": "that was not a JSON object."})
        try:
            if path == "/api/lesson":
                text = str(body.get("text") or "")
                have, new = les.add(self.kb.lessons, text, self.kb.today or date.today())
                return self._json(200, {"ok": True, "new": new, "lessons": len(have)})
            if path == "/api/inbox":
                return self._json(200, {"ok": True, **self._inbox(body)})
            if path in ("/api/advise", "/api/scout", "/api/cards"):
                return self._act(path, body)
            if path == "/api/where":
                self.kb.set_where(body.get("on") is True)
                return self._json(200, {"ok": True, "on": self.kb.where_on()})
            if path == "/api/nudge":
                return self._json(200, {"ok": True, **self._nudge(body)})
            if path == "/api/where/keep":
                return self._json(200, {"ok": True, **self._keep(body)})
            if path not in ("/api/rate", "/api/pick"):
                return self._json(404, {"error": "no such action."})
            log = self.kb.log()
            if not log:
                return self._json(404, {"error": f"no run log at {self.kb.runlog}."})
            try:
                if path == "/api/rate":
                    pieces = body.get("pieces") or []
                    if not isinstance(pieces, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in pieces):
                        raise KeyError("pieces must be a list of piece numbers.")
                    changes = _changes(body.get("changes"))
                    r = rating.rate(log, str(body.get("run") or ""), pieces, str(body.get("worker") or "") or None,
                                    str(body.get("why") or "") or None, changes=[(k, t) for k, t, _ in changes],
                                    kept=[k for k, _, keep in changes if keep])
                    r["lessons_added"] = [les.add(self.kb.lessons, t, self.kb.today or date.today())[1]
                                          for k, t in r["changes"] if k in r["kept"]].count(True)
                else:
                    r = rating.pick(log, str(body.get("run") or ""), str(body.get("worker") or ""))
            finally:
                log.close()
            return self._json(200, {"ok": True, **r})
        except KeyError as e:
            return self._json(400, {"error": str(e.args[0])})
        except Exception as e:                                # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


    def _act(self, path: str, body: dict) -> None:
        """A button on the page: start advice or the scout in the background, or add the cards in one file now."""
        lang = body.get("lang") if body.get("lang") in LABELS else self.kb.lang
        kb = self.kb
        if path == "/api/cards":
            name, text = str(body.get("name") or "cards.md"), body.get("text")
            if not isinstance(text, str):
                raise KeyError("text must be the cards file as text.")
            r = actions.add_cards(kb.picture, kb.cards, name, text, kb.today or date.today())
            kb.cards_said = (time.time(), r)
            return self._json(200, {"ok": True, **cards_say(r, lang)})
        if kb.jobs.state()["status"] == "running":
            return self._json(409, {"say": _t(lang, "busy"), "cls": "err"})
        if not kb.cards_count():
            return self._json(400, {"say": _t(lang, "ask_no_picture"), "cls": "err"})
        names, problem = actions.here_models(kb.models)
        if not names:
            return self._json(400, {"say": _t(lang, "ask_no_models", e=problem or "?"), "cls": "err"})
        if path == "/api/scout":
            from .. import scout
            text = kb.inbox.root / "text"
            if not text.is_dir() or not scout.sources([text]):
                return self._json(400, {"say": _t(lang, "no_inbox_text"), "cls": "err"})
            argv, kind, who = actions.scout_argv(kb, names[0]), "scout", names[:1]
        else:
            argv, kind, who = actions.advise_argv(kb, names, lang), "advise", names
        try:
            state = kb.jobs.start(kind, argv, models=who)
        except actions.Busy:
            return self._json(409, {"say": _t(lang, "busy"), "cls": "err"})
        return self._json(200, {"ok": True, **job_say(state, lang)})

    def _check(self, lang: str) -> str:
        from . import Picture, check
        title = _t(lang, "check_title")
        if not self.kb.picture.exists():
            return doc_page(lang, title, f'<section class="box"><p>{_e(_t(lang, "ask_no_picture"))}</p></section>')
        runs = []
        log = self.kb.log()
        if log:
            try:
                runs = [page.gather(log, r["id"]) for r in query.runs(log, task="advise", limit=10_000)]
            finally:
                log.close()
        c = check.check(Picture.load(self.kb.picture), runs, self.kb.today)
        return doc_page(lang, title, actions.md_html(check.check_md(c), _e), _t(lang, "en_only") if lang != "en" else None)

    def _chances(self, lang: str) -> str:
        from .. import scout
        title = _t(lang, "chances_title")
        rows = scout.Ledger(self.kb.ledger).rows() if self.kb.ledger.exists() else []
        if not rows:
            return doc_page(lang, title, f'<section class="box"><p>{_e(_t(lang, "no_chances_yet"))}</p></section>')
        return doc_page(lang, title, actions.md_html(scout.log_md(rows, self.kb.today), _e),
                        _t(lang, "en_only") if lang != "en" else None)

    def _remember_page(self) -> None:
        """While reminders are on, keep the tailnet address the phone uses, so a tap on a note opens kb."""
        host = (self.headers.get("Host") or "").lower().split(":")[0].rstrip(".")
        if host.endswith(".ts.net"):
            with self.kb.nudge_lock:
                if self.kb.nudge.state()["on"]:
                    self.kb.nudge.remember_page(f"https://{host}/")

    def _nudge(self, body: dict) -> dict:
        """Turn the phone reminders on or off, or send a test note."""
        do = body.get("do")
        lang = body.get("lang") if body.get("lang") in LABELS else self.kb.lang
        if do in ("on", "off"):
            with self.kb.nudge_lock:
                s = self.kb.nudge.turn(do == "on", lang)
            return {"on": s["on"]}
        if do != "test":
            raise KeyError("do must be on, off or test.")
        with self.kb.nudge_lock:
            s = self.kb.nudge.state()
        if not s["on"] or not s["topic"]:
            raise KeyError(_t(lang, "nudge_first"))
        say = nudge.SAY[lang if lang in nudge.SAY else "en"]
        try:
            self.kb.nudge.send(say["test"], say["test_body"], s, 3, "wave", post=self.kb.nudge_post)
        except (URLError, OSError, ValueError) as e:
            raise KeyError(f"ntfy did not take it: {type(e).__name__}: {getattr(e, 'reason', e)}") from None
        return {"say": _t(lang, "nudge_sent")}

    def _keep(self, body: dict) -> dict:
        """A page or a file from Where you were, kept in the inbox: a page as its title and address, a file as a copy.
        Only a file kb just showed you can be kept, never any other path."""
        lang = body.get("lang") if body.get("lang") in LABELS else self.kb.lang
        today = self.kb.today or date.today()
        if not self.kb.where_on():
            raise KeyError("Where you were is off.")
        if body.get("path") is not None:
            path = str(body.get("path"))
            if path not in self.kb.where_paths:
                raise KeyError("kb keeps only a file it showed you under Where you were.")
            f = Path(path)
            if not f.is_file():
                raise KeyError(f"{f.name} is no longer there.")
            if f.stat().st_size > inb.MAX_FILE:
                raise KeyError(_t(lang, "too_big", name=f.name))
            item = self.kb.inbox.add(f.read_bytes(), f.name, None, today, via="laptop")
        else:
            url = wh.clean_url(str(body.get("url") or "").strip())
            if not wh.kind_of(url):
                raise KeyError("kb keeps only web pages (http or https) from Where you were.")
            title = " ".join(str(body.get("title") or "").split())[:300]
            item = self.kb.inbox.add_text(f"{title}\n{url}" if title and title != url else url, None, today, via="laptop")
        return {"say": _t(lang, "kept_one"), "id": item["id"], "new": item["new"]}

    def _inbox(self, body: dict) -> dict:
        """One item a request: {"text": ...} for a post or a link, or {"name", "data" (base64), "note"} for a file."""
        today = self.kb.today or date.today()
        data = body.get("data")
        if data is not None:
            if not isinstance(data, str):
                raise KeyError("data must be the file in base64.")
            try:
                raw = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                raise KeyError("data was not base64.") from None
            name = str(body.get("name") or "") or None
            if (r := self._cards_in(raw, name or "cards.md", today)) is not None:
                return r
            item = self.kb.inbox.add(raw, name, str(body.get("note") or "") or None, today, via="phone")
        else:
            text = str(body.get("text") or "")
            if (r := self._cards_in(text.strip().encode("utf-8"), "pasted cards.md", today)) is not None:
                return r
            item = self.kb.inbox.add_text(text, None, today, via="phone")
        return {k: item[k] for k in ("id", "kind", "status", "new", "name")}

    def _cards_in(self, raw: bytes, name: str, today: date) -> dict | None:
        """A cards file sent to the inbox belongs in the picture: add its cards, as Add cards from a file does.
        None when it holds no PROJECT CARD, so it stays an ordinary inbox item."""
        from . import cards
        if len(raw) > actions.MAX_CARDS or inb.sniff(raw)[0] != "text":
            return None
        text = inb._decode(raw) or ""
        if not cards.parse(text):
            return None
        r = actions.add_cards(self.kb.picture, self.kb.cards, name, text, today)
        self.kb.cards_said = (time.time(), r)
        return {"id": None, "kind": "cards", "status": "cards", "new": bool(r["added"] or r["updated"]), "name": name,
                "found": r["found"], "added": len(r["added"]), "updated": len(r["updated"]), "cards": r["cards"]}


def make(kb: Kb) -> ThreadingHTTPServer:
    """A server bound to 127.0.0.1 only. Call serve_forever() on it; port 0 picks a free port (for tests)."""
    handler = type("KbHandler", (Handler,), {"kb": kb})
    srv = ThreadingHTTPServer(("127.0.0.1", kb.port), handler)
    srv.daemon_threads = True
    if kb.port == 0:
        kb.port = srv.server_address[1]
    return srv
