"""The novel text sanitizer: HTML chapter bodies -> clean plain paragraphs.

The contract every novel connector leans on (spec 2026-09-04-novels-design
§3): no markup, no scripts/styles/ads, no aggregator watermark or self-promo
lines, and only English text gets cached. Exercised against a REAL page —
``tests/fixtures/royalroad/chapter_mol_1.html`` was captured live from the
VPS on 2026-09-04 and contains both a CSS-hidden anti-theft watermark
sentence and inline ad blocks — plus synthesized aggregator watermark lines
in the exact phrasings seen in the wild.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from connectors.novel_text import (
    extract_paragraphs,
    hidden_classes_from_styles,
    is_promo_line,
    looks_english,
    slice_element,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Structural stripping
# ---------------------------------------------------------------------------


def test_strips_scripts_styles_and_ads():
    fragment = """
    <p>First paragraph.</p>
    <script>window.evil = 1;</script>
    <style>.x { color: red }</style>
    <div class="portlet light"><div class="bold uppercase">Advertisement</div>
      <a href="#">buy now</a></div>
    <iframe src="//ads.example.com/slot"></iframe>
    <p>Second paragraph.</p>
    """
    paragraphs = extract_paragraphs(fragment)
    assert paragraphs == ["First paragraph.", "Second paragraph."]


def test_nested_ad_divs_do_not_swallow_following_text():
    fragment = (
        "<p>Before.</p>"
        '<div align="center"><div id="bg-ssp-1"><script>ads()</script></div></div>'
        "<p>After.</p>"
    )
    assert extract_paragraphs(fragment) == ["Before.", "After."]


def test_inline_formatting_is_flattened_and_entities_decoded():
    fragment = "<p>He said &quot;<em>MORNING</em>&quot; &amp; left&hellip;</p>"
    assert extract_paragraphs(fragment) == ['He said "MORNING" & left…']


def test_hidden_class_elements_are_dropped():
    fragment = (
        "<p>Story text.</p>"
        '<span class="cjg3watermark"><br>Stolen content notice.<br></span>'
        "<p>More story.</p>"
    )
    paragraphs = extract_paragraphs(
        fragment, hidden_classes=frozenset({"cjg3watermark"})
    )
    assert paragraphs == ["Story text.", "More story."]


def test_inline_display_none_is_dropped_without_a_class():
    fragment = '<p>Keep.</p><p style="display: none">Drop me.</p><p>Keep too.</p>'
    assert extract_paragraphs(fragment) == ["Keep.", "Keep too."]


def test_hidden_classes_are_read_from_style_blocks():
    html = (
        "<style> .abc123 { display: none; speak: never; } </style>"
        "<div><p class='abc123'>hidden</p></div>"
    )
    assert hidden_classes_from_styles(html) == frozenset({"abc123"})


def test_slice_element_matches_nested_close_tags():
    html = '<div id="article"><p>a</p><div class="ad"><div>x</div></div><p>b</p></div><p>outside</p>'
    inner = slice_element(html, r'<div[^>]*id="article"[^>]*>')
    assert "<p>a</p>" in inner and "<p>b</p>" in inner
    assert "outside" not in inner


# ---------------------------------------------------------------------------
# Watermark / self-promo lines (the aggregator layer)
# ---------------------------------------------------------------------------

PROMO_LINES = [
    "This chapter is updated by freewebnovel.com.",
    # Cyrillic е/с homoglyphs (е, с, о):
    "Updated from freewebnovеl.соm",
    # Latin small-capital E (ᴇ):
    "Follow current novels on novᴇlbin.com",
    "Visit lightnovelworld for the best novel reading experience.",
    "The source of this content is novelfull.net",
    # Zero-width space (​) splitting the domain:
    "New novel chapters are published on freeweb​novel.com",
    "If you spot this narrative on Amazon, know that it has been stolen. Report the violation.",
    "Unauthorized use of content: if you find this story on Amazon, report the violation.",
    "This content is taken from freewebnovel.com",
]

STORY_LINES = [
    "Zorian glared at his little sister, but she just smiled back at him cheekily.",
    'He whispered: "The report is due tomorrow, and the violation of curfew was noted."',
    "The novel virus spread through the city faster than anyone predicted.",
    "She published her findings in the academy journal that spring.",
    "Sunny read the latest entry in his dream journal, frowning at the words.",
]


@pytest.mark.parametrize("line", PROMO_LINES)
def test_promo_lines_are_detected(line):
    assert is_promo_line(line) is True


@pytest.mark.parametrize("line", STORY_LINES)
def test_story_prose_is_never_flagged(line):
    assert is_promo_line(line) is False


def test_extract_drops_promo_lines_from_output():
    fragment = (
        "<p>Real story text here.</p>"
        "<p>This chapter is updated by freewebnovel.com</p>"
        "<p>And the story continues.</p>"
    )
    assert extract_paragraphs(fragment) == [
        "Real story text here.",
        "And the story continues.",
    ]


# ---------------------------------------------------------------------------
# Real captured page: Royal Road chapter with watermark + ads (VPS capture)
# ---------------------------------------------------------------------------


def test_real_royalroad_chapter_is_fully_sanitized():
    html = (FIXTURES / "royalroad" / "chapter_mol_1.html").read_text(
        encoding="utf-8"
    )
    # Prove the capture still carries what this test exists to strip.
    assert "know that it has been stolen" in html
    assert "Advertisement" in html
    hidden = hidden_classes_from_styles(html)
    assert hidden  # the randomized watermark class was found in <style>

    body = slice_element(
        html, r'<div[^>]*class="[^"]*chapter-content[^"]*"[^>]*>'
    )
    assert body is not None
    paragraphs = extract_paragraphs(body, hidden_classes=hidden)

    assert len(paragraphs) > 50
    joined = " ".join(paragraphs)
    assert "Zorian" in joined                      # the story survived
    assert "<" not in joined                       # no markup escaped
    assert "stolen" not in joined.casefold()       # watermark gone
    assert "amazon" not in joined.casefold()
    assert "advertisement" not in joined.casefold()  # ad blocks gone
    assert "javascript" not in joined.casefold()


# ---------------------------------------------------------------------------
# English guard
# ---------------------------------------------------------------------------


def test_english_prose_with_accents_passes():
    assert looks_english(
        [
            "Zoë marched into São Paulo carrying the café's last croissant, "
            "humming a naïve little tune about the Übermensch next door."
        ]
    )


def test_cjk_text_fails():
    assert not looks_english(["重生之最强剑神是一部网络小说，讲述了主角重生回到过去的故事。" * 3])


def test_cyrillic_text_fails():
    assert not looks_english(
        ["Перерождение сильнейшего бога меча — это история о втором шансе." * 3]
    )


def test_tiny_snippets_never_fail():
    assert looks_english(["第一章"])  # too little text to judge
    assert looks_english([])
