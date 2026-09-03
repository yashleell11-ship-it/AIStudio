/**
 * Superseded by the Playwright suite in e2e/ (see playwright.config.ts).
 *
 * This harness drove the pre-1b reader: int-keyed `/reader/chapter/{id}`
 * routes and the local/remote content split, both deleted in the
 * source-native migration. The behaviours it guarded live on as reader unit
 * vitests (fit/spread/scroll-preparation/preload) plus the e2e smoke.
 * Run `npm run test:e2e` instead.
 */
console.log("verify:reader is superseded by e2e/ — run `npm run test:e2e`.");
process.exit(0);
