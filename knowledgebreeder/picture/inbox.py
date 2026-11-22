"""Your inbox: posts, links, screenshots, text, PDFs, Word files and voice notes, kept on this laptop for kb.

Send things from the phone page (kb serve) or with ``kb inbox add``. Everything lands in work/inbox on this machine,
and nothing is sent anywhere. kb reads what it can here and now:

    text and posts      as they are
    links               kept as text; kb never opens a link on its own
    PDF                 the text layer, page by page (a scanned PDF has none, and waits for the image reader)
    Word and PowerPoint the words of a .docx or .pptx file
    screenshots         kept whole; they wait for an image reader that runs on this laptop
    voice notes         kept whole; they wait for a speech reader that runs on this laptop

Nothing is overwritten. The same file sent twice is kept once, with the day it first came; a new note on it is added
beside the old one. A file is known by its content, never by the name it came with, and is never opened or run.

The inbox is three folders:

    items/ID.json            what kb knows about each item: kind, name, size, fingerprint, day, notes, what it read
    files/ID.ext             the item as it came, under a name kb chose
    text/YYYY-MM-DD/ID.txt   the text kb read, with a line saying where it came from

``kb scout read work/inbox/text`` reads that last folder against your picture, so a pasted post becomes a chance
kb can find for you.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

MAX_FILE = 20 * 1024 * 1024          # one item, as it came
MAX_TEXT = 400_000                   # characters of read text kept per item
MAX_UNZIPPED = 40 * 1024 * 1024      # a Word or PowerPoint file may not unpack to more than this
MAX_PAGES = 400

KINDS = ("text", "link", "pdf", "word", "slides", "image", "audio", "other")
STATUS = ("read", "link", "no_text", "waits_image", "waits_speech", "not_read", "empty")
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
_CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def fingerprint(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sniff(data: bytes) -> tuple[str, str]:
    """(kind, extension) from what the bytes are, never from a name or a claimed type."""
    h = data[:64]
    if h.startswith(b"%PDF-"):
        return "pdf", "pdf"
    if h.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            return "other", "bin"
        if "word/document.xml" in names:
            return "word", "docx"
        if any(n.startswith("ppt/slides/slide") for n in names):
            return "slides", "pptx"
        return "other", "zip"
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "png"
    if h.startswith(b"\xff\xd8\xff"):
        return "image", "jpg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image", "webp"
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
            return "image", "heic"
        if brand in (b"avif", b"avis"):
            return "image", "avif"
        return "audio", "m4a" if brand.startswith(b"M4A") else "mp4"
    if h.startswith(b"OggS"):
        return "audio", "ogg"
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return "audio", "wav"
    if h.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio", "webm"
    if h.startswith(b"ID3") or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio", "mp3"
    if h[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return "audio", "aac"
    if h.startswith(b"#!AMR"):
        return "audio", "amr"
    if h.startswith(b"fLaC"):
        return "audio", "flac"
    text = _decode(data)
    if text is not None:
        return ("link", "txt") if _URL.match(text.strip()) else ("text", "txt")
    return "other", "bin"


def _decode(data: bytes) -> str | None:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    try:
        t = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return None if "\x00" in t else t


def _xml_text(xml: str, para: str, run: str) -> str:
    """The words of an Office XML part: one line per paragraph, without an XML parser (nothing to expand)."""
    out = []
    for block in re.split(rf"</{para}>", xml):
        block = re.sub(r"<(?:w|a):tab\s*/>", f"<{run}>\t</{run}>", block)
        block = re.sub(r"<(?:w:br|a:br|w:cr)(?:\s[^>]*)?/>", f"<{run}>\n</{run}>", block)
        line = "".join(re.findall(rf"<{run}(?:\s[^>]*)?>([^<]*)</{run}>", block))
        out.append(html.unescape(line))
    return "\n".join(x.rstrip() for x in out if x.strip()).strip()


def _office(data: bytes, parts: list[str], para: str, run: str) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    texts, total = [], 0
    for name in parts:
        info = z.getinfo(name)
        total += info.file_size
        if total > MAX_UNZIPPED:
            raise ValueError("it unpacks to more than kb reads")
        texts.append(_xml_text(z.read(name).decode("utf-8", "replace"), para, run))
    return "\n\n".join(t for t in texts if t)


def _slides(names: list[str]) -> list[str]:
    nums = sorted(int(m.group(1)) for n in names if (m := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", n)))
    return [f"ppt/slides/slide{i}.xml" for i in nums]


def read(kind: str, data: bytes) -> tuple[str, str, str]:
    """(text, status, why) for an item: what kb could read from it on this laptop."""
    try:
        if kind in ("text", "link"):
            text = _decode(data) or ""
            if not text.strip():
                return "", "empty", "there was nothing in it"
            return text, ("link" if kind == "link" else "read"), ""
        if kind == "pdf":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(data)
            try:
                pages = []
                for i in range(min(len(pdf), MAX_PAGES)):
                    tp = pdf[i].get_textpage()
                    pages.append(tp.get_text_bounded().strip())
                    tp.close()
                more = len(pdf) > MAX_PAGES
            finally:
                pdf.close()
            text = "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages) if p)
            if not text.strip():
                return "", "no_text", "it has no text layer, so it is pictures of pages"
            return text, "read", f"the first {MAX_PAGES} pages" if more else ""
        if kind == "word":
            text = _office(data, ["word/document.xml"], "w:p", "w:t")
            return (text, "read", "") if text.strip() else ("", "empty", "it holds no words")
        if kind == "slides":
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
            text = "\n\n".join(f"[slide {i + 1}]\n{t}" for i, t in
                               enumerate(_office(data, [p], "a:p", "a:t") for p in _slides(names)) if t)
            return (text, "read", "") if text.strip() else ("", "empty", "it holds no words")
        if kind == "image":
            return "", "waits_image", ""
        if kind == "audio":
            return "", "waits_speech", ""
        return "", "not_read", "kb does not read this kind of file"
    except Exception as e:                                       # noqa: BLE001 - a bad file is kept, not fatal
        return "", "not_read", f"it could not be opened ({type(e).__name__})"


def clean_name(name: str | None) -> str:
    """The name a file came with, for showing only: no folders, no control or direction characters."""
    n = _CTRL.sub("", os.path.basename((name or "").replace("\\", "/"))).strip()
    return n[:120]


class Inbox:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def _meta_path(self, iid: str) -> Path:
        return self.root / "items" / f"{iid}.json"

    def get(self, iid: str) -> dict:
        if not re.fullmatch(r"in_[0-9a-f]{12}", iid or ""):
            raise KeyError(f"{iid!r} is not an inbox item. Item names look like in_ and twelve letters or digits.")
        p = self._meta_path(iid)
        if not p.exists():
            raise KeyError(f"no item {iid} in {self.root}. See them all with: kb inbox")
        return json.loads(p.read_text(encoding="utf-8"))

    def text(self, item: dict) -> str:
        p = self.root / item["text_file"] if item.get("text_file") else None
        return p.read_text(encoding="utf-8") if p and p.exists() else ""

    def add(self, data: bytes, name: str | None = None, note: str | None = None, today: date | None = None,
            via: str = "laptop") -> dict:
        """Keep one item. Returns its record, with new=False when the same content was already here."""
        if not data:
            raise KeyError("that was empty.")
        if len(data) > MAX_FILE:
            raise KeyError(f"too big: kb keeps items up to {MAX_FILE // (1024 * 1024)} MB each.")
        today = today or date.today()
        note = _CTRL.sub("", (note or "").strip())[:4000]
        fp = fingerprint(data)
        iid = "in_" + fp[7:19]
        mp = self._meta_path(iid)
        if mp.exists():                                          # nothing overwritten: a new note goes beside the old
            item = json.loads(mp.read_text(encoding="utf-8"))
            if note and note not in [x["text"] for x in item.get("notes", [])]:
                item.setdefault("notes", []).append({"on": today.isoformat(), "text": note})
                self._write(mp, json.dumps(item, ensure_ascii=False, indent=1).encode("utf-8"))
            return {**item, "new": False}
        kind, ext = sniff(data)
        text, status, why = read(kind, data)
        cut = len(text) > MAX_TEXT
        text = text[:MAX_TEXT]
        self._write(self.root / "files" / f"{iid}.{ext}", data)
        item = {"id": iid, "kind": kind, "type": ext, "name": clean_name(name), "size": len(data), "fingerprint": fp,
                "received": today.isoformat(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "via": via, "notes": [{"on": today.isoformat(), "text": note}] if note else [], "status": status,
                "why": why + ("; kb kept the first part of its text" if cut else ""), "file": f"files/{iid}.{ext}",
                "text_file": None, "chars": len(text), "preview": " ".join(text.split())[:200]}
        if text.strip():
            head = [f"Inbox item {iid}, received {item['received']}, a {kind}"
                    + (f" called {item['name']}" if item["name"] else "") + "."]
            if note:
                head.append(f"The note with it: {note}")
            rel = f"text/{item['received']}/{iid}.txt"
            self._write(self.root / rel, ("\n".join(head) + "\n\n" + text.strip() + "\n").encode("utf-8"))
            item["text_file"] = rel
        self._write(mp, json.dumps(item, ensure_ascii=False, indent=1).encode("utf-8"))
        return {**item, "new": True}

    def add_text(self, text: str, note: str | None = None, today: date | None = None, via: str = "laptop") -> dict:
        return self.add((text or "").strip().encode("utf-8"), None, note, today, via)

    def items(self, limit: int | None = None) -> list[dict]:
        """Every item, the newest first."""
        d = self.root / "items"
        if not d.is_dir():
            return []
        out = []
        for p in d.glob("in_*.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        out.sort(key=lambda x: (x.get("at") or "", x.get("id") or ""), reverse=True)
        return out[:limit] if limit else out

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for x in self.items():
            c[x["status"]] = c.get(x["status"], 0) + 1
        return c


SAY = {
    "en": {"read": "read: {n} characters", "link": "a link: kept as text, not opened", "empty": "empty",
           "no_text": "no text layer: waits for the image reader", "waits_image": "waits for the image reader",
           "waits_speech": "waits for the speech reader", "not_read": "kept, not read"},
    "ar": {"read": "قُرئ: {n} حرفًا", "link": "رابط: حُفظ كنص ولم يُفتح", "empty": "فارغ",
           "no_text": "لا نص فيه: ينتظر قارئ الصور", "waits_image": "ينتظر قارئ الصور",
           "waits_speech": "ينتظر قارئ الكلام", "not_read": "محفوظ ولم يُقرأ"},
}


def say(item: dict, lang: str = "en") -> str:
    s = SAY.get(lang, SAY["en"])[item["status"]]
    return s.replace("{n}", f"{item.get('chars', 0):,}")


def list_md(items: list[dict], root: str | Path) -> str:
    if not items:
        return (f"Your inbox at {root} is empty. Send things from the phone page (kb serve), or add files here: "
                "type kb inbox add, a space, and drag the files onto the terminal.\n")
    L = [f"# Your inbox: {len(items)} item{'s' if len(items) != 1 else ''} at {root}", ""]
    for x in items:
        label = x["name"] or x["preview"][:70] or x["kind"]
        L.append(f"- {x['id']}  {x['received']}  {x['kind']}  {label}  ({say(x)})")
        L += [f"    note, {n['on']}: {n['text']}" for n in x.get("notes", [])]
    read_n = sum(1 for x in items if x.get("text_file"))
    if read_n:
        L += ["", f"{read_n} of them have text kb read. To look for chances in them against your picture:",
              f"  kb scout read {Path(root) / 'text'}"]
    waiting = sum(1 for x in items if x["status"] in ("waits_image", "waits_speech", "no_text"))
    if waiting:
        L += ["", (f"{waiting} wait for a reader that runs on this laptop (screenshots, scanned pages, voice notes). "
                   "They are kept whole until then.")]
    return "\n".join(L) + "\n"
