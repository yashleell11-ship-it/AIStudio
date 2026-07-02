"""Generate Toonily connector HTML test fixtures."""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "toonily"


def card(slug: str, title: str) -> str:
    return f"""<div class="page-item-detail manga">
  <div class="item-thumb">
    <a href="https://toonily.com/serie/{slug}/" title="{title}">
      <img src="https://static.tnlycdn.com/{slug}.jpg" alt="{title}">
    </a>
  </div>
</div>"""


def browse(slugs: list[tuple[str, str]], *, page: int = 1, total_pages: int = 2) -> str:
    body = "\n".join(card(slug, title) for slug, title in slugs)
    nav = ""
    if page < total_pages:
        nav = (
            f'<a class="next page-numbers" '
            f'href="https://toonily.com/webtoons/page/{page + 1}/">Next</a>'
        )
    if total_pages > 1:
        nav += "".join(
            f'<a href="https://toonily.com/webtoons/page/{p}/">{p}</a>'
            for p in range(1, total_pages + 1)
        )
    return f'<!DOCTYPE html><html><body><div class="page-listing">{body}</div>{nav}</body></html>'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page1 = [
        ("the-beginning-after-the-end-7b1d8c89", "The Beginning After the End"),
        ("tower-of-god-aa11", "Tower of God"),
        ("noblesse-bb22", "Noblesse"),
        ("god-of-highschool-cc33", "The God of High School"),
        ("eleceed-dd44", "Eleceed"),
        ("lookism-ee55", "Lookism"),
        ("wind-breaker-ff66", "Wind Breaker"),
        ("viral-hit-gg77", "Viral Hit"),
        ("mercenary-enrollment-hh88", "Mercenary Enrollment"),
        ("nano-machine-ii99", "Nano Machine"),
        ("return-of-the-mount-hua-jj00", "Return of the Mount Hua Sect"),
        ("omniscient-reader-kk11", "Omniscient Reader"),
    ]
    page2 = [
        ("solo-leveling-ab12cd34", "Solo Leveling"),
        ("regression-instruction-manual-ll22", "Regression Instruction Manual"),
        ("pick-me-up-mm33", "Pick Me Up"),
        ("dungeon-reset-nn44", "Dungeon Reset"),
        ("player-who-returned-oo55", "Player Who Returned 10,000 Years Later"),
        ("reformation-of-the-deadbeat-noble-pp66", "Reformation of the Deadbeat Noble"),
        ("my-wife-is-a-demon-queen-qq77", "My Wife is a Demon Queen"),
        ("survival-story-rr88", "Survival Story of a Sword King"),
        ("max-level-returner-ss99", "Max Level Returner"),
        ("trash-of-counts-family-tt00", "Trash of the Counts Family"),
        ("villain-to-kill-uu11", "Villain to Kill"),
        ("chronicles-of-heavenly-demon-vv22", "Chronicles of Heavenly Demon"),
    ]
    popular = [
        ("omniscient-reader-kk11", "Omniscient Reader"),
        ("solo-leveling-ab12cd34", "Solo Leveling"),
        *page1[2:],
    ]
    (OUT / "browse_latest.html").write_text(browse(page1), encoding="utf-8")
    (OUT / "browse_page2.html").write_text(browse(page2, page=2), encoding="utf-8")
    (OUT / "browse_popular.html").write_text(browse(popular), encoding="utf-8")
    (OUT / "search_solo.html").write_text(
        browse(
            [
                ("solo-leveling-ab12cd34", "Solo Leveling"),
                ("solo-max-level-newbie-ww33", "Solo Max-Level Newbie"),
            ],
            total_pages=1,
        ),
        encoding="utf-8",
    )
    (OUT / "chapter_reader.html").write_text(
        """<!DOCTYPE html><html><body><div class="reading-content">
<img class="wp-manga-chapter-img" data-src="https://read.tnlycdn.com/tbate/240/001.jpg" src="https://read.tnlycdn.com/tbate/240/001.jpg" />
<img class="wp-manga-chapter-img" data-src="https://read.tnlycdn.com/tbate/240/002.jpg" src="https://read.tnlycdn.com/tbate/240/002.jpg" />
<img class="wp-manga-chapter-img" data-src="https://read.tnlycdn.com/tbate/240/003.jpg" src="https://read.tnlycdn.com/tbate/240/003.jpg" />
</div></body></html>""",
        encoding="utf-8",
    )
    print(f"Wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
