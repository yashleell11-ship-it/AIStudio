"""Generate CoffeeManga connector HTML test fixtures.

The synthetic markup mirrors the live coffeemanga.ink (Madara theme) structure
captured while building the connector, including the quirks the parser must
handle: a manga-title-badges span before the detail <h1>, whitespace inside the
<h5> metadata labels, search results in c-tabs-item__content blocks that also
contain chapter links, and reader images whose URLs carry a leading space
(eager images keep it in src, lazy images in data-src).
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "coffeemanga"

COVER_BASE = "https://coffeemanga.ink/wp-content/uploads/covers"
PAGE_BASE = "https://coffeemanga.ink/wp-content/uploads/WP-manga/data"


def card(post_id: int, slug: str, title: str) -> str:
    return f"""<div class="page-item-detail manga  ">
  <div id="manga-item-{post_id}" class="item-thumb  c-image-hover" data-post-id="{post_id}">
    <a href="https://coffeemanga.ink/manga/{slug}/" title="{title}">
      <img width="175" height="238"  src="{COVER_BASE}/{slug}-175x238.jpeg" srcset="{COVER_BASE}/{slug}-175x238.jpeg 175w" alt="{title}">
    </a>
  </div>
</div>"""


def browse(slugs: list[tuple[str, str]], *, page: int = 1, total_pages: int = 2) -> str:
    body = "\n".join(card(700 + i, slug, title) for i, (slug, title) in enumerate(slugs))
    nav = ""
    if page < total_pages:
        nav = (
            '<a class="next page-numbers" '
            f'href="https://coffeemanga.ink/manga/page/{page + 1}/">Next</a>'
        )
    if total_pages > 1:
        nav += "".join(
            f'<a class="page-numbers" href="https://coffeemanga.ink/manga/page/{p}/">{p}</a>'
            for p in range(2, total_pages + 1)
        )
    return (
        "<!DOCTYPE html><html><body>"
        f'<div class="page-listing-item">{body}</div>'
        f'<div class="wp-pagenav">{nav}</div>'
        "</body></html>"
    )


def search_result(slug: str, title: str) -> str:
    # The series link (with cover) comes first; a chapter link follows in the
    # same block — the parser must return the series, not the chapter.
    return f"""<div class="row c-tabs-item__content">
  <div class="col-4 col-md-2">
    <div class="tab-thumb c-image-hover">
      <a href="https://coffeemanga.ink/manga/{slug}/" title="{title}">
        <img width="193" height="278"  src="{COVER_BASE}/{slug}-193x278.webp" srcset="{COVER_BASE}/{slug}-193x278.webp 193w">
      </a>
    </div>
  </div>
  <div class="col-8 col-md-10">
    <div class="post-title"><h3 class="h4"><a href="https://coffeemanga.ink/manga/{slug}/">{title}</a></h3></div>
    <div class="meta-item latest-chap">
      <span class="font-meta chapter"><a href="https://coffeemanga.ink/manga/{slug}/chapter-22/" title="14 hours ago">Chapter 22</a></span>
    </div>
  </div>
</div>"""


def search(results: list[tuple[str, str]]) -> str:
    body = "\n".join(search_result(slug, title) for slug, title in results)
    return (
        "<!DOCTYPE html><html><body>"
        f'<div class="c-tabs-item">{body}</div>'
        "</body></html>"
    )


def chapter_li(slug: str, segment: str, label: str) -> str:
    return f"""<li class="wp-manga-chapter    ">
        <a href="https://coffeemanga.ink/manga/{slug}/{segment}/">
          {label} </a>
        <span class="chapter-release-date"><a title="2 hours ago" class="c-new-tag">new</a></span>
</li>"""


def series_detail(slug: str, title: str) -> str:
    cover = f"{COVER_BASE}/{slug}.webp"
    # Chapters listed newest-first, as the live site renders them. Includes a
    # decimal side-chapter (chapter-10-5 -> 10.5) between chapter-10 and 11.
    segments = [f"chapter-{n}" for n in range(12, 10, -1)]
    segments += ["chapter-10-5"]
    segments += [f"chapter-{n}" for n in range(10, 0, -1)]
    labels = {
        "chapter-10-5": "Chapter 10.5",
    }
    chapters_html = "\n".join(
        chapter_li(slug, seg, labels.get(seg, f"Chapter {seg.removeprefix('chapter-')}"))
        for seg in segments
    )
    return f"""<!DOCTYPE html><html><head>
<meta property="og:title" content="{title}" />
<meta property="og:image" content="{cover}" />
</head><body>
<div class="post-title">
  <span class="manga-title-badges hot badge-round"><span class="text">Hot</span></span>
  <h1>
      {title}  </h1>
</div>
<div class="summary_image">
  <a href="https://coffeemanga.ink/manga/{slug}/"><img src="{cover}" alt="{title}"></a>
</div>
<div class="post-content_item">
  <div class="summary-heading"><h5>
      Author(s)  </h5></div>
  <div class="summary-content"><div class="author-content"><a href="https://coffeemanga.ink/manga-author/hyeonsol/" rel="tag">HYEONSOL</a></div></div>
</div>
<div class="post-content_item">
  <div class="summary-heading"><h5>
      Artist(s)  </h5></div>
  <div class="summary-content"><div class="artist-content"><a href="https://coffeemanga.ink/manga-artist/hyeonsol/" rel="tag">HYEONSOL</a></div></div>
</div>
<div class="post-content_item">
  <div class="summary-heading"><h5>Genre(s)</h5></div>
  <div class="summary-content"><div class="genres-content">
    <a href="https://coffeemanga.ink/manga-genre/drama/" rel="tag">Drama</a>, <a href="https://coffeemanga.ink/manga-genre/fantasy/" rel="tag">Fantasy</a>, <a href="https://coffeemanga.ink/manga-genre/romance/" rel="tag">Romance</a>
  </div></div>
</div>
<div class="post-content_item">
  <div class="summary-heading"><h5>
      Status  </h5></div>
  <div class="summary-content">
      OnGoing  </div>
</div>
<div class="summary__content show-more">
  <h2>{title}</h2>
  <p>A tragic royal romance about an abandoned prince and his ghostly bride.</p>
</div>
<div class="listing-chapters_wrap">
  <ul class="main version-chap no-volumn">
{chapters_html}
  </ul>
</div>
</body></html>"""


def chapter_reader(slug: str) -> str:
    folder = "manga_6a51122f7b92e/c569eeede5a3954059137039644afa6a"
    # Eager images: real URL in src (leading space), class after src.
    # Lazy images: src is a data-URI placeholder, real URL in data-src (leading space).
    placeholder = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
    eager = "".join(
        f'<img id="image-{i}" src=" {PAGE_BASE}/{folder}/{i + 1}_result.jpg" '
        f'class="wp-manga-chapter-img" loading="eager" fetchpriority="high" decoding="sync">\n'
        for i in range(2)
    )
    lazy = "".join(
        f'<img id="image-{i}" src="{placeholder}" '
        f'class="wp-manga-chapter-img wptangtoc-lazy" loading="lazy" decoding="async" '
        f'data-src=" {PAGE_BASE}/{folder}/{i + 1}_result.webp">\n'
        for i in range(2, 5)
    )
    return (
        "<!DOCTYPE html><html><body>"
        f'<div class="reading-content">\n{eager}{lazy}</div>'
        "</body></html>"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    series_slug = "the-abandoned-princes-ghost-bride"
    series_title = "The Abandoned Prince&#8217;s Ghost Bride"

    page1 = [
        (series_slug, "The Abandoned Prince's Ghost Bride"),
        ("the-monstrous-dukes-adopted-daughter", "The Monstrous Duke's Adopted Daughter"),
        ("the-bosss-shotgun-wedding", "The Boss's Shotgun Wedding"),
        ("solo-max-level-newbie-cf10", "Solo Max-Level Newbie"),
        ("the-remarried-empress-cf11", "The Remarried Empress"),
        ("villains-are-destined-to-die-cf12", "Villains Are Destined to Die"),
    ]
    page2 = [
        ("tower-of-god-cf02", "Tower of God"),
        ("omniscient-reader-cf03", "Omniscient Reader's Viewpoint"),
        ("the-beginning-after-the-end-cf04", "The Beginning After the End"),
        ("lookism-cf05", "Lookism"),
    ]
    popular = [
        ("solo-leveling-cf01", "Solo Leveling"),
        *page1[1:],
    ]

    (OUT / "browse_latest.html").write_text(browse(page1), encoding="utf-8")
    (OUT / "browse_page2.html").write_text(browse(page2, page=2, total_pages=2), encoding="utf-8")
    (OUT / "browse_popular.html").write_text(browse(popular), encoding="utf-8")
    (OUT / "search.html").write_text(
        search(
            [
                (series_slug, "The Abandoned Prince's Ghost Bride"),
                ("the-abandoned-empire-cf20", "The Abandoned Empire"),
            ]
        ),
        encoding="utf-8",
    )
    (OUT / "series_detail.html").write_text(
        series_detail(series_slug, series_title), encoding="utf-8"
    )
    (OUT / "chapter_reader.html").write_text(chapter_reader(series_slug), encoding="utf-8")
    print(f"Wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
