import { expect, test, type Page } from "@playwright/test";

/**
 * The 1b smoke journey (spec §4): login → pick profile → library loads →
 * open a source series → follow → open reader → progress persists.
 *
 * Runs against a live stack (see playwright.config.ts) with credentials from
 * E2E_USERNAME / E2E_PASSWORD; the whole file self-skips when they are unset
 * so `npm run test:e2e` is safe to invoke anywhere.
 *
 * Selectors are user-facing (roles, labels, visible text) so the suite tracks
 * the product, not the DOM.
 */

const USERNAME = process.env.E2E_USERNAME;
const PASSWORD = process.env.E2E_PASSWORD;

test.skip(
  !USERNAME || !PASSWORD,
  "Set E2E_USERNAME and E2E_PASSWORD to run the e2e smoke.",
);

test.describe.configure({ mode: "serial" });

async function signInAndPickProfile(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator("#login-username").fill(USERNAME!);
  await page.locator("#login-password").fill(PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();

  // Login replaces to "/", next.config 307s that to /library, and the app
  // shell bounces to the profile picker when no profile is active yet.
  await page.waitForURL(/\/(library|profiles)/);
  if (new URL(page.url()).pathname.startsWith("/profiles")) {
    await page
      .getByRole("button", { name: /^Read as / })
      .first()
      .click();
    await page.waitForURL(/\/library/);
  }
}

test("login → profile → library → follow a source series → read → progress persists", async ({
  page,
}) => {
  await test.step("login and pick a profile", async () => {
    await signInAndPickProfile(page);
    await expect(page).toHaveURL(/\/library/);
  });

  await test.step("open a source series", async () => {
    await page.goto("/sources");
    // Source cards link to /sources/{id}; series rows link deeper into
    // /sources/{id}/series/{key}.
    await page.locator('a[href^="/sources/"]').first().click();
    await page.waitForURL(/\/sources\/[^/]+$/);
    const seriesLink = page.locator('a[href*="/series/"]').first();
    await expect(seriesLink).toBeVisible();
    await seriesLink.click();
    await page.waitForURL(/\/sources\/[^/]+\/series\//);
  });

  await test.step("follow the series", async () => {
    const followToggle = page.getByRole("button", {
      name: /^(Follow|Unfollow)$/,
    });
    await expect(followToggle).toBeVisible();
    if ((await followToggle.textContent())?.trim() === "Follow") {
      await followToggle.click();
      // POST /library/follow settles and the button flips.
      await expect(
        page.getByRole("button", { name: "Unfollow" }),
      ).toBeVisible();
    }
  });

  await test.step("open the reader and read a little", async () => {
    await page
      .getByRole("link", { name: /^(Read Online|Continue)$/ })
      .click();
    await page.waitForURL(/\/reader\//);
    // A rendered chapter page proves manifest → images resolved end to end.
    await expect(page.locator("img").first()).toBeVisible({
      timeout: 30_000,
    });
    // Scroll far enough that the reader records real progress.
    for (let i = 0; i < 5; i += 1) {
      await page.mouse.wheel(0, 1200);
      await page.waitForTimeout(300);
    }
    // Give the progress push (POST /reader/progress) time to flush.
    await page.waitForTimeout(2_000);
  });

  await test.step("progress persists back on the series page", async () => {
    await page.goBack();
    await page.waitForURL(/\/sources\/[^/]+\/series\//);
    await page.reload();
    // With saved progress the primary CTA reads "Continue", not "Read Online".
    await expect(
      page.getByRole("link", { name: "Continue" }),
    ).toBeVisible();
  });
});
