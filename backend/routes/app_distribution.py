"""Android app distribution + product landing page.

Serves whatever the latest ``flutter build apk --release`` produced, plus a
polished, self-contained landing page so the APK can be installed from a phone
browser on the LAN (and so the project has a real product front door).

The APK path is fixed by the Flutter toolchain and overwritten on every build,
so pointing at that single file always serves the newest APK with no code
change. The version is read live from the Flutter ``pubspec.yaml`` for the same
reason -- bumping the app version needs no edit here.

The landing page is intentionally dependency-free: all CSS/JS is inlined and the
only network calls it makes are same-origin (``/health``, ``/app/download`` and
the bundled screenshots under ``/app/media``), so it renders fully offline on a
LAN with no CDN.
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.config import REPO_ROOT

router = APIRouter(tags=["app"])

# Latest release APK. In the container this is a read-only bind mount populated
# by the deploy (see ops/deploy.sh + docker-compose.yml); ``MM_APK_PATH`` points
# at it. Locally it falls back to the Flutter build output, which Flutter
# overwrites each `flutter build apk --release`, so the path never needs editing.
APK_PATH: Path = Path(
    os.environ.get(
        "MM_APK_PATH",
        str(
            REPO_ROOT
            / "mobile"
            / "build"
            / "app"
            / "outputs"
            / "flutter-apk"
            / "app-release.apk"
        ),
    )
)
# Read live so bumping the app version needs no code change. Overridable via
# ``MM_PUBSPEC_PATH`` since the backend image doesn't ship the mobile project;
# the deploy mounts the pubspec at the default in-container location.
PUBSPEC_PATH: Path = Path(
    os.environ.get("MM_PUBSPEC_PATH", str(REPO_ROOT / "mobile" / "pubspec.yaml"))
)

# Curated marketing screenshots that ship with the mobile project. Served
# read-only under /app/media so the landing page can show the real app. Path is
# env-overridable (``MM_SCREENSHOTS_DIR``) because the backend image doesn't ship
# the mobile project — the deploy mounts the screenshots into the container.
SCREENSHOTS_DIR: Path = Path(
    os.environ.get(
        "MM_SCREENSHOTS_DIR", str(REPO_ROOT / "mobile" / "docs" / "screenshots")
    )
)
_ALLOWED_MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_DEFAULT_VERSION = "1.0.0"
_DEFAULT_BUILD = 1


class AppVersion(BaseModel):
    version: str
    build: int
    apk: str


class ChangelogEntry(BaseModel):
    version: str
    build: int
    date: str
    highlights: list[str]


class Changelog(BaseModel):
    entries: list[ChangelogEntry]


# Human-readable release notes, newest first. Surfaced on the landing page and
# available as JSON at /app/changelog so the mobile "What's new" screen can
# consume the exact same source of truth.
_RELEASE_NOTES: list[ChangelogEntry] = [
    ChangelogEntry(
        version="1.2.2",
        build=5,
        date="July 2026",
        highlights=[
            "Fresh installs from the official download page connect "
            "automatically — no server URL setup screen",
        ],
    ),
    ChangelogEntry(
        version="1.2.1",
        build=4,
        date="July 2026",
        highlights=[
            "Fresh install identity so the app installs cleanly without "
            "uninstalling any earlier build first",
        ],
    ),
    ChangelogEntry(
        version="1.2.0",
        build=3,
        date="July 2026",
        highlights=[
            "Sepia and grayscale reader color modes for late-night reading",
            "High-refresh-rate support up to 120 Hz on capable displays",
            "App-wide haptics and shimmering loading states",
            "Immersive reader transitions and a cross-fading page backdrop",
            "Live performance and display diagnostics",
        ],
    ),
    ChangelogEntry(
        version="1.1.0",
        build=2,
        date="July 2026",
        highlights=[
            "New More control center: history, bookmarks, statistics and storage",
            "In-app update system with one-tap APK download",
            "Redesigned source browser and source list with pinning",
            "Auto-scroll reading mode",
        ],
    ),
    ChangelogEntry(
        version="1.0.0",
        build=1,
        date="July 2026",
        highlights=[
            "First release: library, multi-source browsing and offline reader",
            "Downloads with pause, resume, retry and queueing",
            "Brightness, warm filter and AMOLED-black reader",
        ],
    ),
]


# (icon-key, title, description) — the icon-key maps to an inline SVG below.
_FEATURES: list[tuple[str, str, str]] = [
    (
        "book",
        "Immersive reader",
        "Webtoon-style continuous scroll with tap zones, pinch and double-tap "
        "zoom, and a true fullscreen immersive mode.",
    ),
    (
        "eye",
        "Reader comfort",
        "Brightness, a warm filter and AMOLED-black background, plus sepia and "
        "grayscale color modes that are gentle at 2am.",
    ),
    (
        "bolt",
        "Buttery performance",
        "Decode-at-display-size images, aggressive prefetch, a generous page "
        "cache and up to 120 Hz high-refresh scrolling.",
    ),
    (
        "download",
        "Smart downloads",
        "Queue chapters for offline reading with pause, resume, retry and live "
        "speed and ETA — per chapter, per series, or all at once.",
    ),
    (
        "grid",
        "Personal library",
        "Grid or list with adjustable covers, collections, continue-reading, "
        "recently-updated and your own reading statistics.",
    ),
    (
        "search",
        "Multi-source browsing",
        "Search and browse across every connected source with sorting, "
        "filters, pinning and a cover-first layout.",
    ),
    (
        "refresh",
        "Effortless updates",
        "Your server tells the app when a new build is ready and it installs in "
        "one tap. No store, no waiting.",
    ),
    (
        "shield",
        "Local-first & private",
        "Runs entirely against your own server. No accounts, no ads, no "
        "telemetry — your library never leaves your hardware.",
    ),
]


# (filename, title, caption) — screenshots served from SCREENSHOTS_DIR.
_SHOWCASE: list[tuple[str, str, str]] = [
    (
        "series-detail-screenshot.png",
        "Every series, at a glance",
        "Continue reading, full chapter list and live progress tracking.",
    ),
    (
        "reader-screenshot.png",
        "A reader built for bingeing",
        "Distraction-free pages with per-chapter progress and instant chapter jumps.",
    ),
    (
        "downloads-screenshot.png",
        "Downloads that behave",
        "Pause, resume, retry and reorder — grouped by series with speed and ETA.",
    ),
    (
        "search-screenshot.png",
        "Find your next obsession",
        "Fast search across every source with recent and trending shortcuts.",
    ),
]


# (question, answer)
_FAQ: list[tuple[str, str]] = [
    (
        "Is ManhwaManiacs free?",
        "Yes. It's a personal, local-first reader you run against your own "
        "server. There are no ads, no accounts and no subscriptions.",
    ),
    (
        "Do I need a server?",
        "Yes — the app connects to your ManhwaManiacs backend on your own "
        "machine or LAN. On first launch you simply enter its URL, and you can "
        "change it any time in Settings without restarting.",
    ),
    (
        "Is my reading data private?",
        "Completely. The app talks only to the server URL you configure. "
        "Nothing is sent to us or any third party — there is no telemetry.",
    ),
    (
        "Which sources are supported?",
        "Several manga and manhwa sources plus your own local library. New "
        "connectors are added on the server, so you get more sources without "
        "updating the app.",
    ),
    (
        "How do updates work?",
        "The app checks your server for newer builds and offers a one-tap "
        "download whenever a fresher APK is available on this page.",
    ),
    (
        "Why does Android ask about “unknown sources”?",
        "Because the APK installs straight from your server instead of the Play "
        "Store, Android asks you to allow installs from your browser once. It's "
        "a normal, one-time prompt.",
    ),
]


# Inline stroke icons (24×24, inherit currentColor). Kept tiny and dependency-free.
_ICONS: dict[str, str] = {
    "book": '<path d="M12 6.5C10.5 5 8 4.5 4.5 4.5v13C8 17.5 10.5 18 12 19.5m0-13C13.5 5 16 4.5 19.5 4.5v13C16 17.5 13.5 18 12 19.5m0-13v13"/>',
    "eye": '<circle cx="12" cy="12" r="3"/><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    "download": '<path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "grid": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>',
    "refresh": '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 8m0 0V3m0 5h-5M20 12a8 8 0 0 1-13.7 5.6L4 16m0 0v5m0-5h5"/>',
    "shield": '<path d="M12 3 5 6v5c0 4.4 3 8.5 7 10 4-1.5 7-5.6 7-10V6l-7-3Z"/><path d="m9.5 12 1.8 1.8L15 10"/>',
    "bookmark": '<path d="M7 4h10a1 1 0 0 1 1 1v15l-6-3.5L6 20V5a1 1 0 0 1 1-1Z"/>',
    "phone": '<rect x="6" y="2.5" width="12" height="19" rx="3"/><path d="M10 5.5h4"/>',
}


def read_app_version() -> AppVersion:
    """Parse ``version: x.y.z+b`` from the Flutter pubspec.

    Falls back to sane defaults if the file is missing or malformed so the
    endpoint never 500s just because the mobile project isn't present.
    """
    version = _DEFAULT_VERSION
    build = _DEFAULT_BUILD
    try:
        for line in PUBSPEC_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version:"):
                raw = stripped.split(":", 1)[1].strip().strip("'\"")
                name, _, build_str = raw.partition("+")
                if name.strip():
                    version = name.strip()
                if build_str.strip().isdigit():
                    build = int(build_str.strip())
                break
    except OSError:
        pass
    return AppVersion(version=version, build=build, apk="/app/download")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _icon(key: str) -> str:
    body = _ICONS.get(key, "")
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{body}</svg>'
    )


# ── Section renderers ────────────────────────────────────────────────────────


def _render_nav(info: AppVersion) -> str:
    return f"""
  <header class="nav" id="nav">
    <div class="nav-inner">
      <a class="brand" href="#top" aria-label="ManhwaManiacs home">
        <span class="brand-mark">M</span>
        <span class="brand-name">Manhwa<span class="brand-accent">Maniacs</span></span>
      </a>
      <nav class="nav-links" aria-label="Primary">
        <a href="#features">Features</a>
        <a href="#showcase">Screenshots</a>
        <a href="#whatsnew">What's new</a>
        <a href="#faq">FAQ</a>
        <a href="#support">Support</a>
      </nav>
      <div class="nav-actions">
        <span class="status" id="status" title="Backend status" aria-live="polite">
          <span class="status-dot"></span><span class="status-text">Checking server…</span>
        </span>
        <a class="btn btn-sm" href="#download">Download</a>
      </div>
    </div>
  </header>"""


def _render_hero(info: AppVersion, apk_ready: bool, size_label: str | None) -> str:
    version_pill = escape(f"v{info.version}  ·  build {info.build}")
    size_pill = (
        f'<span class="chip"><span class="chip-dot"></span>{escape(size_label or "")} APK</span>'
        if apk_ready
        else '<span class="chip"><span class="chip-dot"></span>Build pending</span>'
    )
    hero_shot = f"/app/media/{_SHOWCASE[0][0]}?v={info.version}.{info.build}"
    return f"""
  <section class="hero" id="top">
    <div class="aurora" aria-hidden="true">
      <span class="blob b1"></span><span class="blob b2"></span><span class="blob b3"></span>
    </div>
    <div class="hero-inner">
      <div class="hero-copy reveal">
        <span class="eyebrow">Local-first manga &amp; manhwa reader</span>
        <h1 class="hero-title">Your whole library.<br><span class="grad">One beautiful reader.</span></h1>
        <p class="hero-sub">
          ManhwaManiacs turns your personal server into a premium Android reading
          app — immersive reading, smart offline downloads and a library that
          feels like it belongs on the Play Store, running entirely on your own
          hardware.
        </p>
        <div class="hero-cta">
          <a class="btn btn-lg" href="#download">
            {_icon("download")}<span>Download the app</span>
          </a>
          <a class="btn btn-lg btn-ghost" href="#showcase">See it in action</a>
        </div>
        <div class="hero-meta">
          <span class="chip"><span class="chip-dot"></span>{version_pill}</span>
          {size_pill}
          <span class="chip"><span class="chip-dot"></span>No ads · No tracking</span>
        </div>
      </div>
      <div class="hero-art reveal">
        <div class="glow-ring" aria-hidden="true"></div>
        <img class="hero-phone" src="{hero_shot}" alt="ManhwaManiacs series detail screen"
             loading="eager" decoding="async" />
      </div>
    </div>
  </section>"""


def _render_features() -> str:
    cards = "".join(
        f"""
        <article class="feature reveal">
          <span class="feature-icon">{_icon(key)}</span>
          <h3>{escape(title)}</h3>
          <p>{escape(desc)}</p>
        </article>"""
        for key, title, desc in _FEATURES
    )
    return f"""
  <section class="section" id="features">
    <div class="section-head reveal">
      <span class="eyebrow">Everything a reader wants</span>
      <h2>Built to feel premium, everywhere you tap</h2>
      <p class="section-sub">Every screen, gesture and animation is tuned so the
        app disappears and the story stays front and center.</p>
    </div>
    <div class="feature-grid">{cards}</div>
  </section>"""


def _render_showcase(ver: str) -> str:
    shots = "".join(
        f"""
        <figure class="shot reveal">
          <div class="shot-frame">
            <img src="/app/media/{escape(fname)}?v={escape(ver)}" alt="{escape(title)}"
                 loading="lazy" decoding="async" />
          </div>
          <figcaption>
            <h3>{escape(title)}</h3>
            <p>{escape(caption)}</p>
          </figcaption>
        </figure>"""
        for fname, title, caption in _SHOWCASE
    )
    return f"""
  <section class="section section-alt" id="showcase">
    <div class="section-head reveal">
      <span class="eyebrow">A look inside</span>
      <h2>Real screens, no mockup filler</h2>
      <p class="section-sub">This is the actual app — dark by default, tuned for
        AMOLED, and comfortable for hours-long sessions.</p>
    </div>
    <div class="shot-grid">{shots}</div>
  </section>"""


def _render_changelog() -> str:
    entries = "".join(
        f"""
        <article class="release reveal">
          <div class="release-head">
            <span class="release-badge">v{escape(entry.version)}</span>
            <span class="release-date">{escape(entry.date)} · build {entry.build}</span>
          </div>
          <ul class="release-notes">
            {"".join(f"<li>{escape(note)}</li>" for note in entry.highlights)}
          </ul>
        </article>"""
        for entry in _RELEASE_NOTES
    )
    return f"""
  <section class="section" id="whatsnew">
    <div class="section-head reveal">
      <span class="eyebrow">Release notes</span>
      <h2>What's new</h2>
      <p class="section-sub">Shipped continuously. Grab the latest build below.</p>
    </div>
    <div class="release-grid">{entries}</div>
  </section>"""


def _render_download(info: AppVersion, apk_ready: bool, size_label: str | None) -> str:
    if apk_ready:
        action = (
            '<a class="btn btn-xl" href="/app/download">'
            f'{_icon("download")}<span>Download APK</span></a>'
            f'<p class="download-meta">app-release.apk · {escape(size_label or "")} · '
            f"v{escape(info.version)} (build {info.build})</p>"
        )
    else:
        action = (
            '<span class="btn btn-xl btn-disabled">APK not built yet</span>'
            "<p class=\"download-meta\">Run <code>flutter build apk --release</code> "
            "on the server, then refresh this page.</p>"
        )
    steps = [
        ("download", "Download", "Tap the button above to grab the latest signed APK."),
        (
            "shield",
            "Allow the install",
            "When Android asks, allow installs from your browser — a one-time prompt.",
        ),
        (
            "phone",
            "Open & connect",
            "Launch the app and enter your server URL. You're reading in seconds.",
        ),
    ]
    step_html = "".join(
        f"""
        <li class="step reveal">
          <span class="step-num">{i}</span>
          <span class="step-icon">{_icon(key)}</span>
          <div><h4>{escape(title)}</h4><p>{escape(desc)}</p></div>
        </li>"""
        for i, (key, title, desc) in enumerate(steps, start=1)
    )
    return f"""
  <section class="section section-alt" id="download">
    <div class="download-card reveal">
      <div class="download-lead">
        <span class="brand-mark brand-mark-lg">M</span>
        <h2>Get ManhwaManiacs</h2>
        <p class="section-sub">Android 7.0 and up. Installs directly from your
          server — no Play Store required.</p>
        <div class="download-action">{action}</div>
      </div>
      <ol class="steps">{step_html}</ol>
    </div>
  </section>"""


def _render_faq() -> str:
    items = "".join(
        f"""
        <details class="faq-item reveal">
          <summary>{escape(q)}<span class="faq-mark" aria-hidden="true"></span></summary>
          <p>{escape(a)}</p>
        </details>"""
        for q, a in _FAQ
    )
    return f"""
  <section class="section" id="faq">
    <div class="section-head reveal">
      <span class="eyebrow">Good to know</span>
      <h2>Frequently asked</h2>
    </div>
    <div class="faq">{items}</div>
  </section>"""


def _render_support() -> str:
    cards = [
        (
            "book",
            "Documentation",
            "Explore the full backend API in an interactive reference.",
            "/docs",
            False,
        ),
        (
            "bolt",
            "Server status",
            "Check that your backend is online and see its version live.",
            "/health",
            False,
        ),
        (
            "refresh",
            "Release notes",
            "See exactly what changed in every version of the app.",
            "#whatsnew",
            True,
        ),
    ]
    card_html = "".join(
        f"""
        <a class="support-card reveal" href="{escape(href)}"{'' if same else ' target="_blank" rel="noopener"'}>
          <span class="feature-icon">{_icon(key)}</span>
          <div><h3>{escape(title)}</h3><p>{escape(desc)}</p></div>
          <span class="support-arrow" aria-hidden="true">→</span>
        </a>"""
        for key, title, desc, href, same in cards
    )
    return f"""
  <section class="section" id="support">
    <div class="section-head reveal">
      <span class="eyebrow">Get in touch</span>
      <h2>Support &amp; resources</h2>
      <p class="section-sub">ManhwaManiacs is self-hosted, so everything you need
        lives on your own server — here's where to look.</p>
    </div>
    <div class="support-grid">{card_html}</div>
  </section>"""


def _render_footer(info: AppVersion) -> str:
    return f"""
  <footer class="footer">
    <div class="footer-inner">
      <a class="brand" href="#top">
        <span class="brand-mark">M</span>
        <span class="brand-name">Manhwa<span class="brand-accent">Maniacs</span></span>
      </a>
      <p class="footer-note">A local-first reading app for your personal library.
        Runs on your server, answers only to you.</p>
      <div class="footer-links">
        <a href="#features">Features</a>
        <a href="#showcase">Screenshots</a>
        <a href="#whatsnew">What's new</a>
        <a href="#support">Support</a>
        <a href="#download">Download</a>
      </div>
      <p class="footer-fine">ManhwaManiacs · v{escape(info.version)} (build {info.build}) · Made for readers.</p>
    </div>
  </footer>"""


def render_landing_html() -> str:
    """Full, self-contained product landing + APK install page."""
    info = read_app_version()
    apk_ready = APK_PATH.is_file()
    size_label = _format_size(APK_PATH.stat().st_size) if apk_ready else None

    body = (
        _render_nav(info)
        + _render_hero(info, apk_ready, size_label)
        + _render_features()
        + _render_showcase(f"{info.version}.{info.build}")
        + _render_changelog()
        + _render_download(info, apk_ready, size_label)
        + _render_faq()
        + _render_support()
        + _render_footer(info)
    )

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        '  <meta name="color-scheme" content="dark" />\n'
        '  <meta name="theme-color" content="#030507" />\n'
        '  <meta name="description" content="ManhwaManiacs — a premium, local-first '
        'manga and manhwa reader for Android. Immersive reading, smart downloads and a '
        'beautiful library, running on your own server." />\n'
        "  <title>ManhwaManiacs — premium local-first manga &amp; manhwa reader</title>\n"
        f"  <style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        f"  <script>{_JS}</script>\n"
        "</body>\n</html>"
    )


# ── Static styling & behavior (dependency-free) ─────────────────────────────

_CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#030507;--bg2:#080c10;--panel:#0d1117;--panel2:#121a24;
  --border:#1e2633;--border2:#2a3547;
  --fg:#f1f5f9;--muted:#93a0b4;--muted2:#6b7688;
  --primary:#8b5cf6;--primary2:#7c3aed;--violet3:#c4b5fd;
  --accent:#22d3ee;--accent2:#06b6d4;
  --radius:18px;--maxw:1120px;
  --shadow:0 24px 60px rgba(0,0,0,.55);
  --glow:0 12px 40px rgba(139,92,246,.45);
}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--bg);color:var(--fg);
  font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden;
}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}
h1,h2,h3,h4{margin:0;line-height:1.15;letter-spacing:-.02em}
p{margin:0}
.grad{background:linear-gradient(100deg,var(--violet3),var(--primary) 45%,var(--accent) 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.eyebrow{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--violet3);margin-bottom:14px}

/* Buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;
  font-weight:700;border-radius:14px;padding:12px 20px;cursor:pointer;
  color:#fff;background:linear-gradient(135deg,var(--primary),var(--primary2));
  box-shadow:var(--glow);transition:transform .15s ease,box-shadow .15s ease,filter .15s ease;
  border:1px solid rgba(255,255,255,.10)}
.btn svg{width:20px;height:20px}
.btn:hover{transform:translateY(-2px);box-shadow:0 16px 46px rgba(139,92,246,.55)}
.btn:active{transform:translateY(0) scale(.99)}
.btn-sm{padding:9px 16px;font-size:14px;border-radius:12px;box-shadow:none}
.btn-lg{padding:15px 26px;font-size:16px}
.btn-xl{padding:18px 34px;font-size:17px;border-radius:16px;width:100%;max-width:340px}
.btn-ghost{background:rgba(255,255,255,.04);box-shadow:none;color:var(--fg);
  border:1px solid var(--border2)}
.btn-ghost:hover{background:rgba(255,255,255,.08);box-shadow:none}
.btn-disabled{background:rgba(255,255,255,.05);color:var(--muted2);cursor:default;
  box-shadow:none;border:1px solid var(--border)}
.btn-disabled:hover{transform:none}

/* Nav */
.nav{position:sticky;top:0;z-index:50;transition:background .25s ease,border-color .25s ease,backdrop-filter .25s}
.nav-inner{max-width:var(--maxw);margin:0 auto;padding:16px 22px;display:flex;
  align-items:center;gap:20px}
.nav.scrolled{background:rgba(6,8,12,.78);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:11px;font-weight:800;font-size:17px}
.brand-mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
  font-weight:900;color:#fff;background:linear-gradient(135deg,var(--primary),var(--primary2));
  box-shadow:0 8px 22px rgba(139,92,246,.5)}
.brand-mark-lg{width:56px;height:56px;border-radius:16px;font-size:26px;margin-bottom:18px}
.brand-accent{color:var(--violet3)}
.nav-links{margin-left:auto;display:flex;gap:26px;font-size:14px;font-weight:600;color:var(--muted)}
.nav-links a{transition:color .15s}.nav-links a:hover{color:var(--fg)}
.nav-actions{margin-left:auto;display:flex;align-items:center;gap:14px}
.nav-links + .nav-actions{margin-left:26px}
.status{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;
  color:var(--muted);padding:6px 12px;border-radius:999px;border:1px solid var(--border);
  background:rgba(255,255,255,.02)}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--muted2);
  box-shadow:0 0 0 0 rgba(148,160,180,.5)}
.status.online .status-dot{background:#10b981;box-shadow:0 0 12px 1px rgba(16,185,129,.7);
  animation:pulse 2.4s infinite}
.status.offline .status-dot{background:#ef4444}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.55)}70%{box-shadow:0 0 0 8px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}

/* Hero */
.hero{position:relative;overflow:hidden;padding:44px 22px 72px}
.hero-inner{max-width:var(--maxw);margin:0 auto;display:grid;
  grid-template-columns:1.1fr .9fr;gap:48px;align-items:center;position:relative;z-index:2}
.hero-copy{max-width:600px}
.hero-title{font-size:clamp(38px,6vw,62px);font-weight:800;margin-bottom:22px}
.hero-sub{color:var(--muted);font-size:clamp(15px,1.4vw,18px);max-width:540px;margin-bottom:30px}
.hero-cta{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:26px}
.hero-meta{display:flex;flex-wrap:wrap;gap:10px}
.chip{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;
  color:var(--muted);padding:7px 13px;border-radius:999px;border:1px solid var(--border);
  background:rgba(255,255,255,.02)}
.chip-dot{width:6px;height:6px;border-radius:50%;
  background:linear-gradient(135deg,var(--primary),var(--accent))}
.hero-art{position:relative;display:grid;place-items:center}
.hero-phone{width:100%;max-width:440px;border-radius:26px;border:1px solid var(--border2);
  box-shadow:var(--shadow);position:relative;z-index:2}
.glow-ring{position:absolute;width:78%;aspect-ratio:1;border-radius:50%;
  background:radial-gradient(circle,rgba(139,92,246,.42),transparent 66%);filter:blur(20px);z-index:1}
.aurora{position:absolute;inset:0;z-index:1;pointer-events:none}
.blob{position:absolute;border-radius:50%;filter:blur(70px);opacity:.5}
.blob.b1{width:520px;height:520px;top:-180px;left:-120px;
  background:radial-gradient(circle,#6d28d9,transparent 68%);animation:float1 16s ease-in-out infinite}
.blob.b2{width:460px;height:460px;top:-80px;right:-120px;
  background:radial-gradient(circle,#0891b2,transparent 68%);animation:float2 20s ease-in-out infinite}
.blob.b3{width:420px;height:420px;bottom:-220px;left:38%;
  background:radial-gradient(circle,#7c3aed,transparent 70%);animation:float1 24s ease-in-out infinite}
@keyframes float1{0%,100%{transform:translate(0,0)}50%{transform:translate(28px,34px)}}
@keyframes float2{0%,100%{transform:translate(0,0)}50%{transform:translate(-34px,26px)}}

/* Sections */
.section{max-width:var(--maxw);margin:0 auto;padding:76px 22px}
.section-alt{max-width:none;background:
  linear-gradient(180deg,transparent,rgba(139,92,246,.04),transparent),var(--bg2);
  border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.section-alt > *{max-width:var(--maxw);margin-left:auto;margin-right:auto}
.section-head{text-align:center;max-width:640px;margin:0 auto 46px}
.section-head h2{font-size:clamp(27px,3.4vw,40px);font-weight:800;margin-bottom:14px}
.section-sub{color:var(--muted);font-size:16px}

/* Features */
.feature-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}
.feature{background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--border);border-radius:var(--radius);padding:24px 22px;
  transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.feature:hover{transform:translateY(-4px);border-color:var(--border2);
  box-shadow:0 18px 40px rgba(0,0,0,.4)}
.feature-icon{display:grid;place-items:center;width:46px;height:46px;border-radius:13px;
  margin-bottom:16px;color:var(--violet3);
  background:linear-gradient(135deg,rgba(139,92,246,.22),rgba(34,211,238,.12));
  border:1px solid rgba(139,92,246,.28)}
.feature-icon svg{width:23px;height:23px}
.feature h3{font-size:16.5px;margin-bottom:8px}
.feature p{color:var(--muted);font-size:14px}

/* Showcase */
.shot-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:26px}
.shot{margin:0}
.shot-frame{border-radius:20px;overflow:hidden;border:1px solid var(--border2);
  background:#000;box-shadow:var(--shadow);transition:transform .25s ease}
.shot:hover .shot-frame{transform:translateY(-4px) scale(1.005)}
.shot-frame img{width:100%;height:auto}
.shot figcaption{padding:18px 4px 0;text-align:center}
.shot figcaption h3{font-size:18px;margin-bottom:6px}
.shot figcaption p{color:var(--muted);font-size:14px}

/* Release notes */
.release-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.release{background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--border);border-radius:var(--radius);padding:22px}
.release-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.release-badge{font-weight:800;font-size:15px;padding:5px 12px;border-radius:999px;color:#fff;
  background:linear-gradient(135deg,var(--primary),var(--primary2))}
.release-date{color:var(--muted2);font-size:12.5px}
.release-notes{margin:0;padding:0;list-style:none;display:grid;gap:10px}
.release-notes li{position:relative;padding-left:22px;color:var(--muted);font-size:14px}
.release-notes li::before{content:"";position:absolute;left:2px;top:9px;width:8px;height:8px;
  border-radius:2px;background:linear-gradient(135deg,var(--primary),var(--accent))}

/* Download */
.download-card{max-width:var(--maxw);margin:0 auto;display:grid;grid-template-columns:1fr 1fr;
  gap:40px;align-items:center;background:
  radial-gradient(700px 340px at 0% 0%,rgba(139,92,246,.16),transparent 60%),
  linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--border2);border-radius:28px;padding:44px}
.download-lead h2{font-size:clamp(26px,3vw,36px);font-weight:800;margin-bottom:12px}
.download-action{margin-top:26px}
.download-meta{margin-top:14px;color:var(--muted2);font-size:13px}
.download-meta code{color:var(--violet3)}
.steps{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.step{display:flex;align-items:flex-start;gap:14px;background:rgba(255,255,255,.02);
  border:1px solid var(--border);border-radius:14px;padding:16px 18px}
.step-num{flex:none;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;
  font-weight:800;font-size:13px;color:var(--violet3);background:rgba(139,92,246,.16);
  border:1px solid rgba(139,92,246,.3)}
.step-icon{flex:none;color:var(--accent);margin-top:1px}
.step-icon svg{width:20px;height:20px}
.step h4{font-size:15px;margin-bottom:3px}
.step p{color:var(--muted);font-size:13.5px}

/* FAQ */
.faq{max-width:760px;margin:0 auto;display:grid;gap:12px}
.faq-item{background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--border);border-radius:14px;padding:2px 20px;transition:border-color .2s}
.faq-item[open]{border-color:var(--border2)}
.faq-item summary{list-style:none;cursor:pointer;display:flex;align-items:center;
  justify-content:space-between;gap:16px;padding:18px 0;font-weight:600;font-size:15.5px}
.faq-item summary::-webkit-details-marker{display:none}
.faq-mark{flex:none;width:20px;height:20px;position:relative}
.faq-mark::before,.faq-mark::after{content:"";position:absolute;background:var(--violet3);
  border-radius:2px;transition:transform .2s ease}
.faq-mark::before{top:9px;left:2px;width:16px;height:2px}
.faq-mark::after{top:2px;left:9px;width:2px;height:16px}
.faq-item[open] .faq-mark::after{transform:rotate(90deg);opacity:0}
.faq-item p{color:var(--muted);font-size:14.5px;padding:0 0 20px}

/* Support */
.support-grid{max-width:820px;margin:0 auto;display:grid;grid-template-columns:1fr;gap:14px}
.support-card{display:flex;align-items:center;gap:18px;padding:20px 22px;
  background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--border);border-radius:var(--radius);
  transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.support-card:hover{transform:translateY(-3px);border-color:var(--border2);
  box-shadow:0 14px 34px rgba(0,0,0,.4)}
.support-card h3{font-size:16.5px;margin-bottom:4px}
.support-card p{color:var(--muted);font-size:14px}
.support-arrow{margin-left:auto;color:var(--violet3);font-size:20px;font-weight:700;
  transition:transform .2s ease}
.support-card:hover .support-arrow{transform:translateX(4px)}

/* Footer */
.footer{border-top:1px solid var(--border);background:var(--bg2);padding:48px 22px}
.footer-inner{max-width:var(--maxw);margin:0 auto;text-align:center;display:grid;
  gap:16px;justify-items:center}
.footer-note{color:var(--muted);font-size:14px;max-width:440px}
.footer-links{display:flex;gap:22px;flex-wrap:wrap;justify-content:center;
  font-size:14px;font-weight:600;color:var(--muted)}
.footer-links a:hover{color:var(--fg)}
.footer-fine{color:var(--muted2);font-size:12.5px}

/* Reveal on scroll */
.reveal{opacity:0;transform:translateY(22px);
  transition:opacity .6s cubic-bezier(.22,1,.36,1),transform .6s cubic-bezier(.22,1,.36,1)}
.reveal.in{opacity:1;transform:none}

/* Responsive */
@media (max-width:900px){
  .hero-inner{grid-template-columns:1fr;gap:36px}
  .hero-art{order:-1}
  .hero-phone{max-width:300px}
  .feature-grid{grid-template-columns:repeat(2,1fr)}
  .release-grid{grid-template-columns:1fr}
  .download-card{grid-template-columns:1fr;padding:32px}
  .nav-links{display:none}
}
@media (max-width:560px){
  .shot-grid{grid-template-columns:1fr}
  .feature-grid{grid-template-columns:1fr}
  .section{padding:56px 20px}
  .btn-xl{max-width:none}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .reveal{opacity:1;transform:none;transition:none}
  .blob{animation:none}
  .status.online .status-dot{animation:none}
}
"""

_JS = """
(function(){
  var nav=document.getElementById('nav');
  var onScroll=function(){ if(nav) nav.classList.toggle('scrolled', window.scrollY>12); };
  onScroll(); window.addEventListener('scroll',onScroll,{passive:true});

  var reduce=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  var reveals=document.querySelectorAll('.reveal');
  if(reduce||!('IntersectionObserver' in window)){
    reveals.forEach(function(el){el.classList.add('in');});
  } else {
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
    },{threshold:.12,rootMargin:'0px 0px -8% 0px'});
    reveals.forEach(function(el){io.observe(el);});
  }

  var status=document.getElementById('status');
  if(status){
    var text=status.querySelector('.status-text');
    fetch('/health',{headers:{accept:'application/json'}})
      .then(function(r){ return r.ok?r.json():Promise.reject(); })
      .then(function(d){
        status.classList.add('online');
        text.textContent='Server online'+(d&&d.version?(' · v'+d.version):'');
      })
      .catch(function(){ status.classList.add('offline'); text.textContent='Server offline'; });
  }
})();
"""


@router.get("/app/version", response_model=AppVersion)
def app_version() -> AppVersion:
    """Latest app version metadata, read live from the Flutter pubspec."""
    return read_app_version()


@router.get("/app/changelog", response_model=Changelog)
def app_changelog() -> Changelog:
    """Structured release notes, newest first (also shown on the landing page)."""
    return Changelog(entries=_RELEASE_NOTES)


@router.get("/app/media/{name}")
def app_media(name: str) -> FileResponse:
    """Serve a bundled marketing screenshot (read-only, no path traversal)."""
    safe = Path(name).name
    path = SCREENSHOTS_DIR / safe
    if path.suffix.lower() not in _ALLOWED_MEDIA_SUFFIXES or not path.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    return FileResponse(path)


@router.get("/app/download")
def app_download() -> FileResponse:
    """Serve the latest release APK as a download."""
    if not APK_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="APK not built yet. Run `flutter build apk --release`.",
        )
    info = read_app_version()
    return FileResponse(
        path=APK_PATH,
        media_type="application/vnd.android.package-archive",
        filename=f"manhwamaniacs-{info.version}.apk",
    )
