/**
 * The inline script that paints the right palette on the FIRST frame.
 *
 * ### The problem
 *
 * The chosen theme is stored per (user, profile) in localStorage, and the
 * profile is a client-side selection — so the server cannot serialise
 * `data-theme` into the markup, and an effect that sets it only runs after
 * React hydrates. Between those two moments the page paints with the `:root`
 * defaults: Eclipse near-black. At four themes that was a flicker for the two
 * dark ones and a genuine white-to-black blink for Sepia and Daylight. At
 * forty-two it would be the first thing anyone notices on every cold load —
 * exactly the detail that makes a theme system feel bolted on.
 *
 * So the attribute is set before first paint by a blocking script in `<head>`.
 * This is the same trick `next-themes` uses and the only one available to a
 * client-resolved preference: no cookie can carry it, and no media query can
 * express "whatever this profile chose last time".
 *
 * ### Finding the key without knowing the user id
 *
 * `scoped-storage` namespaces keys as `<base>::u<userId>:p<profileId>`, and at
 * boot only the profile id is recoverable — it sits in the zustand-persisted
 * `mm.active-profile` blob. Profile ids are a global autoincrement, so exactly
 * one account owns any given id and matching the `:p<id>` suffix alone cannot
 * cross accounts. Hence the scan.
 *
 * Nothing device-global is read or written. A "last theme used on this device"
 * key would make this half the length and would hand the next profile to open
 * the app the previous one's palette for a frame — a small leak, but of exactly
 * the kind per-profile scoping exists to prevent, and a visible one on a shared
 * screen. With no profile selected (a first visit, the login screen, the
 * picker) the script does nothing and the attribute stays absent, which is what
 * the `:root:not([data-theme])` block in globals.css is for.
 *
 * The source lives in its own module, separate from the component that emits
 * it, so `theme-boot.test.ts` can execute it against a fake `localStorage` and
 * `document`. It is the one piece of this feature that runs before anything
 * else on the page and cannot be debugged from a stack trace.
 */

import { ACTIVE_PROFILE_STORAGE_KEY } from "@/features/profiles/storage-key";
import { READING_THEMES, READING_THEME_STORAGE_BASE } from "./theme";

/**
 * Minified by hand: this is inlined into every HTML response and never sees the
 * bundler. One `try` around the lot — storage access throws outright in a
 * locked-down browser, and a palette is never worth a blank page.
 *
 * Written as a function body rather than an IIFE string so a test can call it
 * with `new Function("localStorage", "document", THEME_BOOT_SOURCE)`; the
 * component wraps it for the page.
 */
export const THEME_BOOT_SOURCE = `try{
var V=${JSON.stringify(READING_THEMES)},P=${JSON.stringify(ACTIVE_PROFILE_STORAGE_KEY)},B=${JSON.stringify(READING_THEME_STORAGE_BASE)};
var raw=localStorage.getItem(P);if(!raw)return;
var p=(JSON.parse(raw).state||{}).activeProfile;if(!p||p.id==null)return;
var suffix=":p"+p.id,prefix=B+"::u";
for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);
if(k&&k.indexOf(prefix)===0&&k.slice(-suffix.length)===suffix){
var t=(localStorage.getItem(k)||"").trim();
if(V.indexOf(t)>=0)document.documentElement.setAttribute("data-theme",t);
return;}}}catch(e){}`;

/** The same source as a self-invoking statement, ready to inline. */
export const THEME_BOOT_SCRIPT = `(function(){${THEME_BOOT_SOURCE}})();`;
