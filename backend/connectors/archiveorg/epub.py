"""EPUB (a ZIP of XHTML + an OPF spine) -> ordered plain-text chapters.

This is the whole reason the archive.org connector exists in a different
shape from every other source. The rest of the fleet serves one chapter per
URL; archive.org serves one *book* per file. So this module is the importer
that turns a book into the chapter list the novel reader expects, and the
connector fetches each book exactly once (see ``connector._load_book``).

Why an EPUB and nothing else:

* The OPF ``<spine>`` is a real, authored reading order, and Project
  Gutenberg / Standard Ebooks both split it per chapter — better structure
  than anything scraped HTML gives us.
* PDF and DjVuTXT are OCR of scanned pages: running headers/footers, page
  numbers and hyphenation damage in every extract, and no dependable chapter
  boundary. A reader (and a future TTS pass) would read that aloud. Items
  without an EPUB are skipped instead — the connector's search query is
  ``format:EPUB``-constrained precisely so this case stays rare.

**No new dependency.** Stdlib ``zipfile`` for the container and the shared
``connectors.novel_text`` sanitizer for the XHTML, exactly as the HTML novel
connectors use it. The OPF/NCX walk is regex-based rather than
``xml.etree`` on purpose: these files are untrusted internet input and
ElementTree happily expands entity bombs, while a regex scan cannot be made
to allocate.

Untrusted-archive guards, all enforced before any decompression:

* ``MAX_MEMBER_BYTES`` / ``MAX_TOTAL_BYTES`` read the ZIP *directory's*
  declared ``file_size`` first, so a zip bomb is refused rather than
  expanded;
* hrefs are resolved with ``posixpath.normpath`` and anything escaping the
  OPF root is dropped (nothing is ever written to disk, but a traversal
  href would still let a crafted book read an unrelated member);
* ``MAX_SPINE_DOCUMENTS`` and ``MAX_BOOK_CHARS`` bound the CPU and the
  memory one book can cost on a 2-vCPU VPS.
"""

from __future__ import annotations

import io
import logging
import posixpath
import re
import zipfile
from dataclasses import dataclass
from html import unescape
from urllib.parse import unquote

from connectors.novel_text import (
    extract_paragraphs,
    hidden_classes_from_styles,
    slice_element,
)

logger = logging.getLogger(__name__)

#: Refuse a single ZIP member, or a whole book, larger than this once
#: decompressed. Read from the ZIP directory before any read() happens.
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 48 * 1024 * 1024

#: Spine documents examined per book, and total sanitized characters kept.
#: Both exist to bound one request's cost on the VPS (2 vCPU); a legitimate
#: novel is far under either.
MAX_SPINE_DOCUMENTS = 1500
MAX_BOOK_CHARS = 8_000_000

#: A spine document with fewer real words than this is front/back matter --
#: a title page, a dedication, a half title. Tuned against the fixtures:
#: Standard Ebooks' Preface (76 words) and Dracula's "Note" epilogue (347)
#: must survive; its Dedication (5) and Titlepage (0) must not.
MIN_CHAPTER_WORDS = 50

#: EPUB 3 ``epub:type`` values that mark a document as apparatus rather than
#: the work. Deliberately specific: the coarse ``frontmatter`` / ``backmatter``
#: values are NOT here, because Standard Ebooks tags a real Preface
#: ``frontmatter`` and a real epilogue ``backmatter``.
BOILERPLATE_EPUB_TYPES = frozenset(
    {
        "cover",
        "titlepage",
        "halftitlepage",
        "fulltitle",
        "imprint",
        "colophon",
        "copyright-page",
        "toc",
        "landmarks",
        "loi",
        "lot",
        "frontispiece",
    }
)

#: Project Gutenberg wraps every book in licence text, sometimes as its own
#: spine document and sometimes glued onto the first/last real one. These
#: markers are the official banner lines; text before the START banner and
#: from the END banner onward is licence, not book.
_PG_START_MARKER = re.compile(
    r"\*\*\*\s*START OF (?:TH(?:IS|E)|)\s*PROJECT GUTENBERG", re.IGNORECASE
)
_PG_END_MARKER = re.compile(
    r"\*\*\*\s*END OF (?:TH(?:IS|E)|)\s*PROJECT GUTENBERG"
    r"|\*\*\*\s*START:\s*FULL LICEN[SC]E"
    r"|THE FULL PROJECT GUTENBERG LICEN[SC]E",
    re.IGNORECASE,
)

_XHTML_MEDIA_TYPES = frozenset(
    {"application/xhtml+xml", "text/html", "application/x-dtbook+xml"}
)

_ENCODING_RE = re.compile(
    r"""<\?xml[^>]*encoding\s*=\s*["']([\w.-]+)["']|<meta[^>]*charset\s*=\s*["']?([\w.-]+)""",
    re.IGNORECASE,
)
_ATTR_CACHE: dict[str, re.Pattern[str]] = {}


@dataclass(frozen=True, slots=True)
class EpubChapter:
    """One readable spine document, already sanitized.

    ``key`` is the manifest href relative to the OPF directory -- it lives in
    the book file itself, so re-parsing the same EPUB yields the same key.
    ``number`` is the 1-based position in the *readable* spine (apparatus
    already dropped), which keeps chapter numbers contiguous for the reader's
    furthest-wins progress merge.
    """

    key: str
    title: str
    number: float
    paragraphs: tuple[str, ...]

    @property
    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


@dataclass(frozen=True, slots=True)
class ParsedEpub:
    """A whole book: OPF metadata plus its readable chapters, in order."""

    title: str | None
    author: str | None
    language: str | None
    chapters: tuple[EpubChapter, ...]


def _attr(tag: str, name: str) -> str:
    """One attribute value out of an already-matched open tag."""
    pattern = _ATTR_CACHE.get(name)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(name)}\s*=\s*\"([^\"]*)\"|\b{re.escape(name)}\s*=\s*'([^']*)'", re.IGNORECASE)
        _ATTR_CACHE[name] = pattern
    match = pattern.search(tag)
    if match is None:
        return ""
    return unescape(match.group(1) if match.group(1) is not None else match.group(2))


def _decode(raw: bytes) -> str:
    """Decode a book member, honouring its own declared encoding."""
    head = raw[:1024].decode("ascii", "replace")
    match = _ENCODING_RE.search(head)
    encoding = (match.group(1) or match.group(2)) if match else None
    for candidate in (encoding, "utf-8", "latin-1"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


class _Book:
    """Size-guarded reader over one in-memory EPUB ZIP."""

    def __init__(self, blob: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(blob))
        self._budget = MAX_TOTAL_BYTES
        # Case-insensitive index: a handful of EPUBs disagree with themselves
        # about the case of a href.
        self._members = {name.lower(): name for name in self._zip.namelist()}

    def read(self, path: str) -> str | None:
        name = self._members.get(path.lower())
        if name is None:
            return None
        try:
            info = self._zip.getinfo(name)
        except KeyError:
            return None
        # Declared size first: never expand a bomb to find out how big it is.
        if info.file_size > MAX_MEMBER_BYTES or info.file_size > self._budget:
            logger.warning(
                "archive.org EPUB member %s refused (%d bytes declared)",
                name,
                info.file_size,
            )
            return None
        try:
            raw = self._zip.read(name)
        except (KeyError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
            logger.warning("archive.org EPUB member %s unreadable: %s", name, exc)
            return None
        self._budget -= len(raw)
        return _decode(raw)

    def names(self) -> list[str]:
        return list(self._members.values())


def _resolve(base_dir: str, href: str) -> str | None:
    """OPF-relative href -> ZIP member path, or None when it escapes the book."""
    href = unquote(href.split("#", 1)[0]).strip()
    if not href or href.startswith(("http://", "https://", "data:")):
        return None
    joined = posixpath.join(base_dir, href) if base_dir else href
    normalized = posixpath.normpath(joined).lstrip("/")
    if normalized in (".", "..") or normalized.startswith("../"):
        return None
    return normalized


def _opf_path(book: _Book) -> str | None:
    container = book.read("META-INF/container.xml")
    if container:
        match = re.search(r"<rootfile\b[^>]*>", container, re.IGNORECASE)
        if match:
            full_path = _attr(match.group(0), "full-path")
            if full_path:
                return full_path.lstrip("/")
    # Malformed container: fall back to the only .opf in the archive.
    candidates = [n for n in book.names() if n.lower().endswith(".opf")]
    return candidates[0] if len(candidates) == 1 else None


def _dc(opf: str, tag: str) -> str | None:
    match = re.search(rf"<dc:{tag}\b[^>]*>(.*?)</dc:{tag}>", opf, re.IGNORECASE | re.DOTALL)
    if match is None:
        match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", opf, re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", match.group(1)))).strip()
    return text or None


def _manifest(opf: str) -> dict[str, tuple[str, str, str]]:
    """manifest id -> (href, media-type, properties)."""
    items: dict[str, tuple[str, str, str]] = {}
    manifest_block = slice_element(opf, r"<manifest[^>]*>") or opf
    for tag in re.findall(r"<item\b[^>]*?/?>", manifest_block):
        item_id = _attr(tag, "id")
        href = _attr(tag, "href")
        if item_id and href:
            items[item_id] = (href, _attr(tag, "media-type").lower(), _attr(tag, "properties").lower())
    return items


def _spine(opf: str) -> list[tuple[str, bool]]:
    """[(idref, linear)] in reading order."""
    block = slice_element(opf, r"<spine[^>]*>")
    if block is None:
        return []
    entries: list[tuple[str, bool]] = []
    for tag in re.findall(r"<itemref\b[^>]*?/?>", block):
        idref = _attr(tag, "idref")
        if idref:
            entries.append((idref, _attr(tag, "linear").lower() != "no"))
    return entries


def _toc_labels(book: _Book, base_dir: str, manifest: dict[str, tuple[str, str, str]]) -> dict[str, str]:
    """href (no fragment) -> the title the book's own TOC gives that document.

    Reads both TOC dialects: the EPUB 2 NCX ``navMap`` and the EPUB 3 nav
    document. First label wins, so a document split across several TOC
    entries takes the first one -- which is its heading.
    """
    labels: dict[str, str] = {}

    def remember(href: str, text: str) -> None:
        href = unquote(href.split("#", 1)[0]).strip()
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text))).strip()
        if href and text:
            labels.setdefault(href, text)

    ncx_href = next(
        (href for href, media, _ in manifest.values() if media == "application/x-dtbncx+xml"),
        None,
    )
    if ncx_href is None:
        ncx_href = next((n for n in book.names() if n.lower().endswith(".ncx")), None)
        ncx_path = ncx_href
    else:
        ncx_path = _resolve(base_dir, ncx_href)
    if ncx_path:
        ncx = book.read(ncx_path)
        if ncx:
            for point in re.findall(r"<navPoint\b.*?</navPoint>", ncx, re.DOTALL | re.IGNORECASE):
                text = re.search(r"<text\b[^>]*>(.*?)</text>", point, re.DOTALL | re.IGNORECASE)
                content = re.search(r"<content\b[^>]*>", point, re.IGNORECASE)
                if text and content:
                    remember(_attr(content.group(0), "src"), text.group(1))

    nav_href = next((href for href, _, props in manifest.values() if "nav" in props.split()), None)
    nav_path = _resolve(base_dir, nav_href) if nav_href else None
    if nav_path:
        nav = book.read(nav_path)
        if nav:
            nav_dir = posixpath.dirname(nav_href or "")
            for anchor in re.finditer(r"<a\b([^>]*)>(.*?)</a>", nav, re.DOTALL | re.IGNORECASE):
                href = _attr("<a" + anchor.group(1) + ">", "href")
                if href:
                    remember(posixpath.normpath(posixpath.join(nav_dir, href)) if nav_dir else href, anchor.group(2))
    return labels


def _epub_types(document: str) -> frozenset[str]:
    """``epub:type`` tokens from the document's outermost elements.

    Only the first few carriers are read (``<body>``, the wrapping
    ``<section>``): a token found on some inline ``<a epub:type="noteref">``
    deep in a chapter says nothing about what the document *is*.
    """
    tokens: set[str] = set()
    for match in re.finditer(r"epub:type\s*=\s*\"([^\"]*)\"|epub:type\s*=\s*'([^']*)'", document[:4000], re.IGNORECASE):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        tokens.update(t.strip().lower() for t in (value or "").split())
        if len(tokens) > 12:
            break
    return frozenset(tokens)


def _strip_gutenberg_licence(paragraphs: list[str]) -> list[str]:
    """Drop the Project Gutenberg header/licence wrapper around the book.

    Truncating rather than dropping the whole document matters: some PG
    conversions glue the END banner onto the last real chapter, and dropping
    that document would silently lose a chapter of the book.
    """
    start = 0
    for index, paragraph in enumerate(paragraphs):
        if _PG_START_MARKER.search(paragraph):
            start = index + 1
    trimmed = paragraphs[start:]
    for index, paragraph in enumerate(trimmed):
        if _PG_END_MARKER.search(paragraph):
            return trimmed[:index]
    return trimmed


def _document_title(
    labels: dict[str, str], href: str, document: str, position: int
) -> str:
    """The book's own name for a document: TOC label, heading, then <title>."""
    label = labels.get(unquote(href.split("#", 1)[0]))
    if label:
        return label
    for pattern in (r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", r"<title\b[^>]*>(.*?)</title>"):
        match = re.search(pattern, document, re.DOTALL | re.IGNORECASE)
        if match:
            text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", match.group(1)))).strip()
            if text:
                return text
    return f"Part {position}"


def parse_epub(blob: bytes) -> ParsedEpub | None:
    """Whole EPUB bytes -> metadata + readable chapters, or None if unusable.

    None means "this book cannot be served": not a ZIP, no OPF, no spine, or
    nothing in the spine survived the apparatus filters. The connector treats
    that exactly like a missing series rather than serving a shell.
    """
    try:
        book = _Book(blob)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        logger.warning("archive.org EPUB is not a readable ZIP: %s", exc)
        return None

    opf_path = _opf_path(book)
    if not opf_path:
        logger.warning("archive.org EPUB has no OPF package document")
        return None
    opf = book.read(opf_path)
    if not opf:
        logger.warning("archive.org EPUB OPF %s unreadable", opf_path)
        return None

    base_dir = posixpath.dirname(opf_path)
    manifest = _manifest(opf)
    spine = _spine(opf)
    if not spine:
        logger.warning("archive.org EPUB %s has an empty spine", opf_path)
        return None
    labels = _toc_labels(book, base_dir, manifest)

    chapters: list[EpubChapter] = []
    budget = MAX_BOOK_CHARS
    for idref, linear in spine[:MAX_SPINE_DOCUMENTS]:
        if not linear:
            continue  # linear="no": cover wrappers and pop-up notes.
        entry = manifest.get(idref)
        if entry is None:
            continue
        href, media_type, _props = entry
        if media_type and media_type not in _XHTML_MEDIA_TYPES:
            continue
        path = _resolve(base_dir, href)
        if path is None:
            continue
        document = book.read(path)
        if not document:
            continue
        if _epub_types(document) & BOILERPLATE_EPUB_TYPES:
            continue

        body = slice_element(document, r"<body[^>]*>")
        if body is None:
            body = document
        paragraphs = _strip_gutenberg_licence(
            extract_paragraphs(body, hidden_classes=hidden_classes_from_styles(document))
        )
        if sum(len(p.split()) for p in paragraphs) < MIN_CHAPTER_WORDS:
            continue

        budget -= sum(len(p) for p in paragraphs)
        if budget < 0:
            logger.warning(
                "archive.org EPUB %s exceeded the %d-char book budget at chapter %d",
                opf_path,
                MAX_BOOK_CHARS,
                len(chapters) + 1,
            )
            break

        position = len(chapters) + 1
        chapters.append(
            EpubChapter(
                key=href.split("#", 1)[0],
                title=_document_title(labels, href, document, position),
                number=float(position),
                paragraphs=tuple(paragraphs),
            )
        )

    if not chapters:
        logger.warning("archive.org EPUB %s yielded no readable chapters", opf_path)
        return None

    return ParsedEpub(
        title=_dc(opf, "title"),
        author=_dc(opf, "creator"),
        language=_dc(opf, "language"),
        chapters=tuple(chapters),
    )
