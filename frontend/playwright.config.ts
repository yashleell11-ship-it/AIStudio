import { defineConfig, devices } from "@playwright/test";

/**
 * E2E smoke config (spec §4). Runs against an ALREADY-RUNNING full stack —
 * the Next dev/prod server on E2E_BASE_URL with the FastAPI backend behind
 * its /api proxy. Nothing is mocked: the flow exercises real auth, profiles,
 * sources, and reader progress, so it needs a reachable source upstream.
 *
 *   E2E_BASE_URL   default http://localhost:3000
 *   E2E_USERNAME   account to sign in with (required — no default on purpose)
 *   E2E_PASSWORD   its password
 *
 *   npm run test:e2e          # after: npx playwright install chromium
 *
 * Kept entirely out of the vitest gate: vitest only includes src/**\/*.test.ts
 * and explicitly excludes e2e/.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // The smoke is one continuous user journey; steps depend on prior steps.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
