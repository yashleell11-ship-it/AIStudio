/**
 * End-to-end reader verification harness.
 *
 * Run with the frontend dev server already listening on :3000:
 *   npm run verify:reader
 */
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import zlib from "node:zlib";

const BASE_URL = process.env.VERIFY_BASE_URL ?? "http://localhost:3000";
const API_URL = process.env.VERIFY_API_URL ?? "http://127.0.0.1:8000";
const NAV_OPTS = { waitUntil: "domcontentloaded", timeout: 20_000 };

const TALL_PAGE_RATIO = 8; // height / width, like AsuraScans webtoon strips

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

/** Solid-color PNG of arbitrary size, for tall dimensionless page fixtures. */
function makePng(width, height) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // color type RGB
  const scanlines = Buffer.alloc(height * (1 + width * 3), 0x30);
  for (let y = 0; y < height; y += 1) {
    scanlines[y * (1 + width * 3)] = 0; // filter: none
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(scanlines)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

const TALL_PNG = makePng(64, 64 * TALL_PAGE_RATIO);
// Pages are declared as 800x1200; the served image must have the same 2/3
// ratio because the reader lays loaded pages out at their intrinsic size.
const PAGE_PNG = makePng(8, 12);

const results = [];

function record(name, pass, details = "") {
  results.push({ name, pass, details });
  const mark = pass ? "PASS" : "FAIL";
  console.log(`[${mark}] ${name}${details ? ` — ${details}` : ""}`);
}

function makeLocalChapter(chapterId, pageCount) {
  return {
    id: chapterId,
    series_id: 1,
    title: `Local Chapter ${chapterId}`,
    number: chapterId,
    page_count: pageCount,
    pages: Array.from({ length: pageCount }, (_, index) => ({
      id: chapterId * 10_000 + index + 1,
      number: index + 1,
      width: 800,
      height: 1200,
    })),
  };
}

function makeRemoteChapter(chapterId, pageCount, { dimensionless = false } = {}) {
  const imagePrefix = dimensionless ? "mock-tall-image" : "mock-image";
  return {
    mode: "remote",
    source_id: "mangadex",
    series_id: "series-verify",
    id: String(chapterId),
    title: `Online Chapter ${chapterId}`,
    page_count: pageCount,
    pages: Array.from({ length: pageCount }, (_, index) => ({
      id: `${chapterId}-page-${index + 1}`,
      number: index + 1,
      width: dimensionless ? null : 800,
      height: dimensionless ? null : 1200,
      image_url: `${API_URL}/${imagePrefix}/${chapterId}/${index + 1}.png`,
    })),
    previous_chapter_id: null,
    next_chapter_id: null,
  };
}

async function installApiMocks(page) {
  await page.route(`${API_URL}/**`, async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;

    if (pathname.startsWith("/updates/")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "0",
      });
    }

    if (pathname.startsWith("/library/")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0, page: 1, per_page: 200 }),
      });
    }

    if (pathname.startsWith("/reader/page/") && pathname.endsWith("/image")) {
      return route.fulfill({
        status: 200,
        contentType: "image/png",
        body: PAGE_PNG,
      });
    }

    if (pathname.startsWith("/mock-image/")) {
      return route.fulfill({
        status: 200,
        contentType: "image/png",
        body: PAGE_PNG,
      });
    }

    if (pathname.startsWith("/mock-tall-image/")) {
      return route.fulfill({
        status: 200,
        contentType: "image/png",
        body: TALL_PNG,
      });
    }

    const localChapterMatch = pathname.match(/^\/reader\/chapter\/(\d+)$/);
    if (localChapterMatch) {
      const chapterId = Number(localChapterMatch[1]);
      const pageCount = chapterId === 900 ? 350 : 12;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(makeLocalChapter(chapterId, pageCount)),
      });
    }

    const remoteChapterMatch = pathname.match(
      /^\/sources\/mangadex\/series\/([^/]+)\/chapters\/([^/]+)\/reader$/,
    );
    if (remoteChapterMatch) {
      const chapterId = remoteChapterMatch[2];
      if (chapterId === "950") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            makeRemoteChapter(chapterId, 6, { dimensionless: true }),
          ),
        });
      }
      const pageCount = chapterId === "900" ? 350 : 12;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(makeRemoteChapter(chapterId, pageCount)),
      });
    }

    if (pathname.match(/^\/reader\/chapter\/\d+\/adjacent$/)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
    }

    if (pathname === "/reader/bookmarks" && route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 1,
          series_id: 1,
          chapter_id: 1,
          page: 1,
          note: null,
          created_at: new Date().toISOString(),
        }),
      });
    }

    if (pathname === "/reader/progress" && route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          series_id: 1,
          chapter_id: 1,
          last_page: 1,
          progress_pct: 0,
          last_read_at: new Date().toISOString(),
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "{}",
    });
  });
}

async function seedStaleScroll(page) {
  await page.evaluate(() => {
    const main = document.querySelector("main");
    if (main) {
      main.scrollTop = 2400;
    }
  });
}

async function waitForReaderImages(page) {
  await page.waitForSelector("main img", { timeout: 15_000 });
  await page.waitForFunction(
    () => {
      const images = Array.from(document.querySelectorAll("main img"));
      return images.some((img) => img.complete && img.naturalWidth > 0);
    },
    { timeout: 15_000 },
  );
}

async function gotoLocalChapter(page, chapterId) {
  await page.goto(`${BASE_URL}/reader/1/${chapterId}`, NAV_OPTS);
}

async function gotoOnlineChapter(page, chapterId) {
  await page.goto(
    `${BASE_URL}/reader/online/mangadex/series-verify/${chapterId}`,
    NAV_OPTS,
  );
}

async function openLocalChapter(page, chapterId, { seedStale = true } = {}) {
  if (seedStale) {
    await seedStaleScroll(page);
  }

  const imageRequests = [];
  const listener = (request) => {
    const url = request.url();
    if (url.includes("/reader/page/") || url.includes("/mock-image/")) {
      imageRequests.push({ url, time: Date.now() });
    }
  };
  page.on("request", listener);

  const startedAt = Date.now();
  await gotoLocalChapter(page, chapterId);
  await waitForReaderImages(page);
  const firstImageDelay = imageRequests.length > 0 ? imageRequests[0].time - startedAt : -1;

  page.off("request", listener);
  return { imageRequests, firstImageDelay };
}

async function openOnlineChapter(page, chapterId, { seedStale = true } = {}) {
  if (seedStale) {
    await seedStaleScroll(page);
  }

  const imageRequests = [];
  const listener = (request) => {
    const url = request.url();
    if (url.includes("/mock-image/") || url.includes("/reader/page/")) {
      imageRequests.push({ url, time: Date.now() });
    }
  };
  page.on("request", listener);

  const startedAt = Date.now();
  await gotoOnlineChapter(page, chapterId);
  await waitForReaderImages(page);
  const firstImageDelay = imageRequests.length > 0 ? imageRequests[0].time - startedAt : -1;

  page.off("request", listener);
  return { imageRequests, firstImageDelay };
}

async function assertNoBlackScreen(page) {
  const loadingVisible = await page
    .getByText("Loading chapter…")
    .isVisible()
    .catch(() => false);
  const hasVisibleImage = await page.evaluate(() => {
    const images = Array.from(document.querySelectorAll("main img"));
    return images.some((img) => img.complete && img.naturalWidth > 0);
  });
  return !loadingVisible && hasVisibleImage;
}

async function leaveReader(page) {
  await page.goto(`${BASE_URL}/library`, NAV_OPTS);
  await page.waitForSelector("main");
}

async function testScrollPersistence(page, { scrollKey, openChapter, chapterId }) {
  await page.evaluate((key) => localStorage.removeItem(`manhwamaniacs-reader-scroll:${key}`), scrollKey);

  await openChapter(page, chapterId, { seedStale: true });
  await waitForReaderImages(page);

  const targetScroll = await page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return 0;
    main.scrollTop = 2400;
    main.dispatchEvent(new Event("scroll", { bubbles: true }));
    return main.scrollTop;
  });
  await page.waitForTimeout(400);

  await leaveReader(page);
  await seedStaleScroll(page);

  await openChapter(page, chapterId, { seedStale: false });
  await waitForReaderImages(page);

  const restoredScroll = await page.evaluate(() => document.querySelector("main")?.scrollTop ?? 0);
  const savedScroll = await page.evaluate(
    (key) => Number(localStorage.getItem(`manhwamaniacs-reader-scroll:${key}`)),
    scrollKey,
  );

  return { targetScroll, savedScroll, restoredScroll };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  await installApiMocks(page);

  await page.goto(`${BASE_URL}/library`, NAV_OPTS);
  await page.waitForSelector("main");
  await seedStaleScroll(page);

  // 1. Thirty consecutive online chapters
  let onlineFailures = 0;
  let onlineSlowOpens = 0;
  for (let chapterId = 1; chapterId <= 30; chapterId += 1) {
    const { imageRequests, firstImageDelay } = await openOnlineChapter(page, chapterId);
    const ok = await assertNoBlackScreen(page);
    if (!ok) onlineFailures += 1;
    if (imageRequests.length === 0 || firstImageDelay > 1500) onlineSlowOpens += 1;
  }
  record(
    "30 consecutive online chapters",
    onlineFailures === 0,
    `${30 - onlineFailures}/30 rendered, ${onlineSlowOpens} slow/no-image opens`,
  );

  // 2. Thirty consecutive local/downloaded chapters
  let localFailures = 0;
  let localSlowOpens = 0;
  for (let chapterId = 1; chapterId <= 30; chapterId += 1) {
    const { imageRequests, firstImageDelay } = await openLocalChapter(page, chapterId);
    const ok = await assertNoBlackScreen(page);
    if (!ok) localFailures += 1;
    if (imageRequests.length === 0 || firstImageDelay > 1500) localSlowOpens += 1;
  }
  record(
    "30 consecutive local/downloaded chapters",
    localFailures === 0,
    `${30 - localFailures}/30 rendered, ${localSlowOpens} slow/no-image opens`,
  );

  // 3. Alternate local and online readers
  let alternateFailures = 0;
  for (let index = 1; index <= 10; index += 1) {
    await openLocalChapter(page, 100 + index);
    if (!(await assertNoBlackScreen(page))) alternateFailures += 1;
    await openOnlineChapter(page, 100 + index);
    if (!(await assertNoBlackScreen(page))) alternateFailures += 1;
  }
  record(
    "Alternate local and online readers",
    alternateFailures === 0,
    `${20 - alternateFailures}/20 opens rendered`,
  );

  // 4. Refresh while inside a chapter
  await page.evaluate((key) => localStorage.removeItem(`manhwamaniacs-reader-scroll:${key}`), "501");
  await openLocalChapter(page, 501);
  const refreshTargetScroll = await page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return 0;
    main.scrollTop = 2200;
    main.dispatchEvent(new Event("scroll", { bubbles: true }));
    return main.scrollTop;
  });
  await page.waitForTimeout(400);
  await page.reload(NAV_OPTS);
  await waitForReaderImages(page);
  const refreshScroll = await page.evaluate(() => document.querySelector("main")?.scrollTop ?? 0);
  record(
    "Browser refresh inside chapter",
    (await assertNoBlackScreen(page)) && refreshScroll >= 2000,
    `target=${refreshTargetScroll}, restored=${refreshScroll}`,
  );

  // 5. Open chapter from bookmarked URL with page offset
  await seedStaleScroll(page);
  await page.goto(`${BASE_URL}/reader/1/502?page=5`, NAV_OPTS);
  await waitForReaderImages(page);
  const bookmarkScroll = await page.evaluate(() => document.querySelector("main")?.scrollTop ?? 0);
  record(
    "Bookmarked URL deep-link",
    bookmarkScroll > 0 && (await assertNoBlackScreen(page)),
    `scrollTop=${bookmarkScroll}`,
  );

  // 6. No black screen on stale-scroll first open
  await seedStaleScroll(page);
  const staleOpen = await openLocalChapter(page, 503);
  record(
    "No black screen on stale-scroll first open",
    (await assertNoBlackScreen(page)) && staleOpen.imageRequests.length > 0,
    `${staleOpen.imageRequests.length} image requests`,
  );

  // 7. Image requests begin immediately on first open
  record(
    "Image requests begin immediately on first open",
    staleOpen.firstImageDelay >= 0 && staleOpen.firstImageDelay <= 1500,
    `first image after ${staleOpen.firstImageDelay}ms`,
  );

  // 8. Virtualization on 300+ page chapter
  await openLocalChapter(page, 900);
  const virtualStats = await page.evaluate(() => ({
    mountedImages: document.querySelectorAll("main img").length,
    scrollHeight: document.querySelector("main")?.scrollHeight ?? 0,
  }));
  record(
    "Virtualization on 350-page chapter",
    virtualStats.mountedImages > 0 && virtualStats.mountedImages < 80,
    `${virtualStats.mountedImages} mounted images, scrollHeight=${virtualStats.scrollHeight}`,
  );

  // 9. Scroll restoration after leave and reopen (local)
  const localScroll = await testScrollPersistence(page, {
    scrollKey: "888",
    chapterId: 888,
    openChapter: openLocalChapter,
  });
  record(
    "Scroll restoration (local leave and reopen)",
    localScroll.savedScroll >= 2000 && localScroll.restoredScroll >= 2000,
    `saved=${localScroll.savedScroll}, restored=${localScroll.restoredScroll}`,
  );

  // 9b. Scroll restoration after leave and reopen (online)
  const onlineScroll = await testScrollPersistence(page, {
    scrollKey: "mangadex:series-verify:889",
    chapterId: 889,
    openChapter: openOnlineChapter,
  });
  record(
    "Scroll restoration (online leave and reopen)",
    onlineScroll.savedScroll >= 2000 && onlineScroll.restoredScroll >= 2000,
    `saved=${onlineScroll.savedScroll}, restored=${onlineScroll.restoredScroll}`,
  );

  // 10. No unnecessary image requests while scrolling
  const imageRequests = new Set();
  const requestListener = (request) => {
    const url = request.url();
    if (url.includes("/reader/page/") || url.includes("/mock-image/")) {
      imageRequests.add(url);
    }
  };
  page.on("request", requestListener);
  await openLocalChapter(page, 900);
  await page.evaluate(async () => {
    const main = document.querySelector("main");
    if (!main) return;
    for (let step = 0; step < 8; step += 1) {
      main.scrollTop += 900;
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
  });
  await page.waitForTimeout(500);
  page.off("request", requestListener);
  record(
    "No unnecessary image requests while scrolling",
    imageRequests.size < 120,
    `${imageRequests.size} unique image requests during partial scroll of 350 pages`,
  );

  // 11. Browser Back button restores chapter and scroll
  await page.evaluate((key) => localStorage.setItem(`manhwamaniacs-reader-scroll:${key}`, "1800"), "777");
  await seedStaleScroll(page);
  await gotoLocalChapter(page, 777);
  await waitForReaderImages(page);
  await leaveReader(page);
  await page.goBack(NAV_OPTS);
  await waitForReaderImages(page);
  const backScroll = await page.evaluate(() => document.querySelector("main")?.scrollTop ?? 0);
  record(
    "Browser Back button restores chapter scroll",
    backScroll >= 1700 && (await assertNoBlackScreen(page)),
    `scrollTop=${backScroll}`,
  );

  // 12. Zoom controls update rendered zoom level (local)
  await openLocalChapter(page, 600, { seedStale: false });
  const zoomBefore = await page.getByRole("button", { name: "Reset zoom" }).textContent();
  await page.getByRole("button", { name: "Zoom in" }).click();
  const zoomAfter = await page.getByRole("button", { name: "Reset zoom" }).textContent();
  record(
    "Zoom controls adjust reader zoom (local)",
    zoomBefore === "100%" && zoomAfter === "110%",
    `${zoomBefore} -> ${zoomAfter}`,
  );

  // 12b. Zoom controls work identically on online reader
  await openOnlineChapter(page, 603, { seedStale: false });
  const onlineZoomBefore = await page.getByRole("button", { name: "Reset zoom" }).textContent();
  await page.getByRole("button", { name: "Zoom in" }).click();
  const onlineZoomAfter = await page.getByRole("button", { name: "Reset zoom" }).textContent();
  const onlineBeforePct = Number.parseInt(onlineZoomBefore ?? "0", 10);
  const onlineAfterPct = Number.parseInt(onlineZoomAfter ?? "0", 10);
  record(
    "Zoom controls adjust reader zoom (online)",
    onlineAfterPct === onlineBeforePct + 10,
    `${onlineZoomBefore} -> ${onlineZoomAfter}`,
  );

  // 13. Bookmark button triggers save request (local reader)
  let bookmarkPosted = false;
  const bookmarkListener = (request) => {
    if (request.url().includes("/reader/bookmarks") && request.method() === "POST") {
      bookmarkPosted = true;
    }
  };
  page.on("request", bookmarkListener);
  await openLocalChapter(page, 601, { seedStale: false });
  await page.getByRole("button", { name: "Bookmark" }).click();
  await page.waitForTimeout(300);
  page.off("request", bookmarkListener);
  record("Bookmark button saves page", bookmarkPosted);

  // 14. Online and local readers both load images on stale-scroll first open
  await seedStaleScroll(page);
  const localStale = await openLocalChapter(page, 602);
  await seedStaleScroll(page);
  const onlineStale = await openOnlineChapter(page, 602);
  record(
    "Online and local behave identically on stale-scroll first open",
    localStale.imageRequests.length > 0 &&
      onlineStale.imageRequests.length > 0 &&
      (await assertNoBlackScreen(page)),
    `local=${localStale.imageRequests.length} reqs, online=${onlineStale.imageRequests.length} reqs`,
  );

  // 15. Deep scroll restoration on a 350-page chapter
  const deepScroll = await testScrollPersistence(page, {
    scrollKey: "900",
    chapterId: 900,
    openChapter: openLocalChapter,
  });
  record(
    "Deep scroll restoration on 350-page chapter",
    deepScroll.savedScroll >= 2000 && deepScroll.restoredScroll >= 2000,
    `saved=${deepScroll.savedScroll}, restored=${deepScroll.restoredScroll}`,
  );

  // 16. Dimensionless tall pages render at full natural height (no clipping).
  //     Regression guard for AsuraScans: pages arrive without width/height and
  //     can be 900x16000 strips; the old 2/3 aspect-ratio box clipped ~86% of
  //     the chapter's pixels, which read as "missing pages".
  await openOnlineChapter(page, 950, { seedStale: false });
  await page.waitForFunction(
    () => {
      const img = document.querySelector("main [data-page='1'] img");
      return img && img.complete && img.naturalWidth > 0;
    },
    { timeout: 15_000 },
  );
  await page.waitForTimeout(400);
  const tallPageStats = await page.evaluate(() => {
    const row = document.querySelector("main [data-page='1']");
    const img = row?.querySelector("img");
    if (!row || !img) return null;
    const box = img.parentElement.getBoundingClientRect();
    return {
      boxWidth: box.width,
      boxHeight: box.height,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
    };
  });
  const neededHeight = tallPageStats
    ? (tallPageStats.boxWidth / tallPageStats.naturalWidth) * tallPageStats.naturalHeight
    : 0;
  record(
    "Dimensionless tall pages render unclipped",
    tallPageStats != null &&
      tallPageStats.naturalHeight / tallPageStats.naturalWidth > 4 &&
      Math.abs(tallPageStats.boxHeight - neededHeight) <= 2,
    tallPageStats
      ? `box=${tallPageStats.boxWidth.toFixed(0)}x${tallPageStats.boxHeight.toFixed(0)}, needs height ${neededHeight.toFixed(0)}`
      : "page row not found",
  );

  await browser.close();

  const failed = results.filter((entry) => !entry.pass);
  const reportPath = path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "verify-reader-report.json",
  );
  writeFileSync(reportPath, JSON.stringify({ results, failed: failed.length }, null, 2));

  console.log(`\nVerification report written to ${reportPath}`);
  if (failed.length > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
