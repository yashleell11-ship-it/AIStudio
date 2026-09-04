"""HTML chapter bodies -> sanitized plain-text paragraphs (spec 2026-09-04 §3).

Shared by every novel connector. The contract: paragraphs that leave this
module are CLEAN — no markup, no scripts/styles, no ad blocks, no aggregator
watermark or self-promo lines, entities decoded, whitespace normalized. They
are the canonical storage form (``novel_chapter_cache``) and the exact text a
future TTS pipeline will read, so anything that would sound wrong spoken
aloud is this module's problem.

Two independent defense layers:

1. **Structural** (``extract_paragraphs``): an ``html.parser`` walk that keeps
   only real text content. Script/style/iframe/form/ins/etc. subtrees are
   dropped wholesale, as is any element carrying a class from
   ``hidden_classes`` — Royal Road hides its anti-theft watermark sentences
   with per-chapter randomized classes styled ``display: none``
   (``hidden_classes_from_styles`` collects them from the page's ``<style>``
   blocks), and FreeWebNovel interleaves ``<div>``-wrapped ad slots between
   paragraphs.

2. **Textual** (``is_promo_line``): a phrase blacklist for watermark lines
   that are *visible* text (aggregators inject "updated by <domain>" /
   "read the latest chapters at <domain>" sentences directly into the body).
   Matched against a normalized form (NFKC-folded, zero-width characters
   stripped) so Unicode-confusable obfuscation ("freewebnovᴇl") does not
   slip through.
"""

from __future__ import annotations

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser

# Subtrees that can never contribute chapter text.
_DROP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "iframe",
        "ins",
        "form",
        "button",
        "select",
        "svg",
        "canvas",
        "audio",
        "video",
        "figure",
        "img",
    }
)

# Elements whose boundary ends the current paragraph.
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "blockquote",
        "section",
        "article",
        "hr",
        "table",
        "ul",
        "ol",
    }
)

# class/id tokens that mark an ad slot wherever they appear. Token-matched
# (never substring) so story-adjacent words ("shadow", "download") are safe.
_AD_TOKENS = frozenset(
    {
        "ad",
        "ads",
        "advert",
        "adverts",
        "advertisement",
        "advertisements",
        "adsbygoogle",
        "adslot",
        "adbox",
        "adx",
        "ssp",
        "sponsored",
        "banner",
        "portlet",  # Royal Road's in-chapter ad blocks
    }
)
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")

# ``<style>`` rules that hide an element. Royal Road's watermark classes are
# randomized per fetch, so they must be read out of the page itself.
_HIDDEN_RULE_RE = re.compile(
    r"\.([A-Za-z0-9_-]+)\s*\{[^}]*display\s*:\s*none",
    re.IGNORECASE,
)

# Zero-width/formatting characters used to break up blacklist phrases
# (ZWSP, ZWNJ, ZWJ, word joiner, BOM, soft hyphen).
_ZERO_WIDTH_RE = re.compile("[\\u200b\\u200c\\u200d\\u2060\\ufeff\\u00ad]")

# Homoglyphs aggregators use to dodge phrase filters ("freewebnovеl.соm" with
# Cyrillic е/с, "novᴇlbin" with small caps). NFKC does NOT fold these — they
# are distinct letters, not compatibility forms — so they get an explicit map.
_CONFUSABLES = str.maketrans(
    {
        # Cyrillic lookalikes.
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
        "у": "y", "і": "i", "ѕ": "s", "ԁ": "d", "ј": "j", "ԛ": "q",
        "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Х": "X",
        "У": "Y", "І": "I", "Ѕ": "S", "Ј": "J",
        # Latin small capitals / phonetic letters.
        "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f",
        "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l",
        "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ꜱ": "s",
        "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴢ": "z",
        "ɡ": "g",
    }
)

# Visible watermark / self-promo lines seen in aggregator chapter bodies and
# stolen-content notices. Matched against whole normalized paragraphs; every
# pattern here must be specific enough that it can never fire on story prose.
_PROMO_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # The aggregators naming themselves.
        r"freewebnovel\s*[.,]?\s*com",
        r"free\s*web\s*novel\b",
        r"libread\s*[.,]?\s*com",
        r"novel(?:bin|full|fire|next|hall|hi)\s*[.,]?\s*(?:com|net|me|co)",
        r"lightnovel(?:world|pub)",
        r"\bwebnovel\s*[.,]?\s*com",
        r"royalroad\s*[.,]?\s*com",
        # Generic "this text came from <site>" injections.
        r"(?:updated|published|posted|uploaded)\s+(?:by|from|first|on)\s+(?:this\s+)?[a-z0-9-]+\s*[.,]\s*(?:com|net|org|me|co|io)\b",
        r"(?:read|find|follow|support)\s+(?:the\s+)?(?:latest|new(?:est)?)\s+(?:novels?|chapters?|stories)\s+(?:at|on|only\s+(?:at|on))\b",
        r"(?:the\s+)?source\s+of\s+this\s+(?:content|chapter|story)\b",
        r"content\s+is\s+taken\s+from\b",
        r"chapters?\s+(?:are\s+)?published\s+on\b",
        r"search\s+the\s+\S+\s+website\s+on\s+google\b",
        # Royal Road's stolen-content notices (normally hidden via CSS; this
        # is the fallback if the structural layer misses one).
        r"(?:if\s+you\s+(?:spot|find|encounter|come\s+across)\s+this\s+(?:story|narrative|tale)|this\s+(?:story|narrative|tale)\s+has\s+been)\s+.{0,60}\b(?:amazon|stolen|unlawfully|without\s+(?:the\s+author'?s?\s+)?(?:consent|permission))",
        r"\breport\s+(?:the|any)\s+(?:violation|infringement|occurrence)s?\b",
        r"(?:stolen|taken)\s+from\s+royal\s+road\b",
        r"unauthorized\s+(?:use|duplication|reproduction|repost)",
        r"this\s+(?:content|novel|chapter|book|story)\s+is\s+taken\s+from\b",
    )
)


def hidden_classes_from_styles(html_text: str) -> frozenset[str]:
    """Class names any ``<style>`` block on the page styles ``display: none``."""
    classes: set[str] = set()
    for style in re.findall(
        r"<style[^>]*>(.*?)</style>", html_text, re.IGNORECASE | re.DOTALL
    ):
        classes.update(_HIDDEN_RULE_RE.findall(style))
    return frozenset(classes)


def normalize_line(text: str) -> str:
    """Whitespace-collapsed, NFKC- and confusable-folded promo-match form."""
    text = _ZERO_WIDTH_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CONFUSABLES)
    return re.sub(r"\s+", " ", text).strip()


def is_promo_line(paragraph: str) -> bool:
    """True when a paragraph is a watermark/self-promo line, not story text."""
    normalized = normalize_line(paragraph).casefold()
    if not normalized:
        return False
    return any(p.search(normalized) for p in _PROMO_PATTERNS)


class _ParagraphExtractor(HTMLParser):
    """Collect visible text as paragraphs, skipping dropped/hidden subtrees."""

    def __init__(self, hidden_classes: frozenset[str]) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_classes = hidden_classes
        # Depth counter instead of a flag: dropped subtrees nest (an ad div
        # containing a script containing ...); text is visible only at 0.
        self._suppressed_depth = 0
        # Void elements never come back through handle_endtag, so they must
        # not touch the suppression counter.
        self._void_tags = frozenset(
            {"br", "hr", "img", "input", "meta", "link", "area", "base",
             "col", "embed", "source", "track", "wbr"}
        )
        self._parts: list[str] = []
        self._paragraphs: list[str] = []

    def _is_hidden(self, attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name == "class" and value:
                if any(cls in self._hidden_classes for cls in value.split()):
                    return True
            if name in ("class", "id") and value:
                tokens = (t.lower() for t in _TOKEN_SPLIT_RE.split(value) if t)
                if any(token in _AD_TOKENS for token in tokens):
                    return True
            if name == "style" and value:
                if re.search(r"display\s*:\s*none", value, re.IGNORECASE):
                    return True
        return False

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
        self._parts = []
        if text:
            self._paragraphs.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            # A hard break inside a paragraph splits it: RR bolded chapter
            # headings use <br> between "Chapter 001" and the title.
            self._flush()
            return
        if tag in self._void_tags:
            return
        if self._suppressed_depth:
            self._suppressed_depth += 1
            return
        if tag in _DROP_TAGS or self._is_hidden(attrs):
            self._suppressed_depth = 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._void_tags:
            return
        if self._suppressed_depth:
            self._suppressed_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._suppressed_depth and data:
            self._parts.append(data)

    def result(self) -> list[str]:
        self._flush()
        return self._paragraphs


def extract_paragraphs(
    fragment: str,
    *,
    hidden_classes: frozenset[str] = frozenset(),
) -> list[str]:
    """Sanitize one chapter-body HTML fragment into plain-text paragraphs.

    Structural strip (scripts/styles/ads/hidden elements) plus the promo-line
    blacklist. The output is what gets cached and served — see module docstring.
    """
    parser = _ParagraphExtractor(hidden_classes)
    parser.feed(fragment)
    parser.close()
    return [
        unescape_stray(p) for p in parser.result() if not is_promo_line(p)
    ]


def unescape_stray(paragraph: str) -> str:
    """Decode entities the parser left as literal text (double-escaped pages)."""
    return unescape(paragraph)


def looks_english(paragraphs: tuple[str, ...] | list[str]) -> bool:
    """Conservative English check for a chapter that claims to be English.

    Every novel source shipped here serves English text (originals or
    translations), but aggregators occasionally leak an untranslated raw or a
    non-English mirror page; caching that into ``novel_chapter_cache`` would
    pin garbage for a week. Heuristic: of all alphabetic characters, at least
    70% must be plain ASCII letters. English prose with accented names ("Zoë
    marched into São Paulo") is ~99% ASCII letters and passes easily; CJK or
    Cyrillic text is ~0% and fails hard. Too little text to judge (< 40
    letters) passes — never fail a chapter on an epigraph.
    """
    text = " ".join(paragraphs)
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 40:
        return True
    ascii_letters = sum(1 for ch in letters if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    return ascii_letters / len(letters) >= 0.7


def slice_element(html_text: str, open_tag_pattern: str) -> str | None:
    """Inner HTML of the first element whose open tag matches the pattern.

    Chapter bodies nest ad ``<div>``s inside the content ``<div>``, so a
    "until the next ``</div>``" slice truncates mid-chapter; this walks
    open/close tags of the same name and returns the region up to the
    *matching* close. ``open_tag_pattern`` must match the full opening tag
    (e.g. ``r'<div[^>]*class="[^"]*chapter-content[^"]*"[^>]*>'``).
    """
    opened = re.search(open_tag_pattern, html_text, re.IGNORECASE)
    if opened is None:
        return None
    tag_name = re.match(r"<\s*([a-zA-Z0-9]+)", opened.group(0))
    if tag_name is None:
        return None
    tag = tag_name.group(1).lower()
    token_re = re.compile(rf"<{tag}\b[^>]*>|</{tag}\s*>", re.IGNORECASE)
    depth = 0
    for token in token_re.finditer(html_text, opened.start()):
        if token.group(0).startswith("</"):
            depth -= 1
        elif not token.group(0).endswith("/>"):
            depth += 1
        if depth == 0:
            return html_text[opened.end() : token.start()]
    # Unbalanced markup: better the tail (the extractor still sanitizes it)
    # than nothing.
    return html_text[opened.end() :]
