/**
 * The inline script that paints the right APPEARANCE on the FIRST frame.
 *
 * Appearance is two independent choices — the palette (`data-theme`, ~42 of
 * them) and the design preset (`data-preset`, five) — and both have the same
 * problem for the same reason, so one script solves it once for both.
 *
 * ### The problem
 *
 * Both choices are stored per (user, profile) in localStorage, and the profile
 * is a client-side selection — so the server cannot serialise either attribute
 * into the markup, and an effect that sets them only runs after React hydrates.
 * Between those two moments the page paints with the `:root` defaults: GitHub
 * Dark near-black, Signature glass. At four themes that was a flicker for the
 * two dark ones and a genuine white-to-black blink for Sepia and Daylight. At
 * forty-two it would be the first thing anyone notices on every cold load —
 * exactly the detail that makes a theme system feel bolted on. The preset is
 * less violent (nobody's retina reacts to a corner radius) but it is more
 * structural: Compact and Editorial reflow the page, so hydrating into the
 * wrong one means the whole layout jumps once the store resolves.
 *
 * So both attributes are set before first paint by a blocking script in
 * `<head>`. This is the same trick `next-themes` uses and the only one
 * available to a client-resolved preference: no cookie can carry it, and no
 * media query can express "whatever this profile chose last time".
 *
 * ### Finding the keys without knowing the user id
 *
 * `scoped-storage` namespaces keys as `<base>::u<userId>:p<profileId>`, and at
 * boot only the profile id is recoverable — it sits in the zustand-persisted
 * `mm.active-profile` blob. Profile ids are a global autoincrement, so exactly
 * one account owns any given id and matching the `:p<id>` suffix alone cannot
 * cross accounts. Hence the scan, which both attributes share: the matching
 * rule is subtle enough (a suffix match that must not treat `:p1` as `:p21`)
 * that having two hand-minified copies of it would be a bug with a countdown
 * on it.
 *
 * Nothing device-global is read or written. A "last appearance used on this
 * device" key would make this half the length and would hand the next profile
 * to open the app the previous one's look for a frame — a small leak, but of
 * exactly the kind per-profile scoping exists to prevent, and a visible one on
 * a shared screen. With no profile selected the script does nothing and both
 * attributes stay absent, which is what the `:root:not([data-theme])` block and
 * the bare `:root` shape defaults in globals.css are for.
 *
 * ### Why it declines on /login and /register
 *
 * A persisted profile id outlives the session it was chosen in, so on the auth
 * screens this could apply a look for a viewer who is not signed in — while the
 * stores, which need the session too, would resolve to the defaults and
 * repaint. That is a flash in the opposite direction, and it would also
 * announce on a shared machine what the last person here reads in. Those
 * screens belong to nobody yet, so they get the defaults — which is why the
 * default palette has to be one the app is happy to be seen in rather than a
 * placeholder: /login and /register wear it start to finish.
 *
 * The source lives in its own module, separate from the component that emits
 * it, so `appearance-boot.test.ts` can execute it against a fake `localStorage`
 * and `document`. It is the one piece of this feature that runs before anything
 * else on the page and cannot be debugged from a stack trace.
 */

import { PUBLIC_AUTH_PATHS } from "@/features/auth/access";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/features/profiles/storage-key";
import { DESIGN_PRESETS, DESIGN_PRESET_STORAGE_BASE } from "./presets";
import { READING_THEMES, READING_THEME_STORAGE_BASE } from "./theme";

/**
 * What to look for, and where to put it: `[storage base, attribute, allowed
 * values]`. Adding a third axis here is the whole of what it takes to give it
 * first-paint support.
 */
const CHANNELS: readonly [string, string, readonly string[]][] = [
  [READING_THEME_STORAGE_BASE, "data-theme", READING_THEMES],
  [DESIGN_PRESET_STORAGE_BASE, "data-preset", DESIGN_PRESETS],
];

/**
 * Minified by hand: this is inlined into every HTML response and never sees the
 * bundler. One `try` around the lot — storage access throws outright in a
 * locked-down browser, and an appearance is never worth a blank page.
 *
 * Written as a function body rather than an IIFE string so a test can call it
 * with `new Function("localStorage", "document", APPEARANCE_BOOT_SOURCE)`; the
 * component wraps it for the page.
 */
export const APPEARANCE_BOOT_SOURCE = `try{
var C=${JSON.stringify(CHANNELS)},P=${JSON.stringify(ACTIVE_PROFILE_STORAGE_KEY)};
if(${JSON.stringify(PUBLIC_AUTH_PATHS)}.indexOf(location.pathname.replace(/\\/+$/,"")||"/")>=0)return;
var raw=localStorage.getItem(P);if(!raw)return;
var p=(JSON.parse(raw).state||{}).activeProfile;if(!p||p.id==null)return;
var suffix=":p"+p.id;
for(var c=0;c<C.length;c++){var prefix=C[c][0]+"::u";
for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);
if(k&&k.indexOf(prefix)===0&&k.slice(-suffix.length)===suffix){
var v=(localStorage.getItem(k)||"").trim();
if(C[c][2].indexOf(v)>=0)document.documentElement.setAttribute(C[c][1],v);
break;}}}}catch(e){}`;

/** The same source as a self-invoking statement, ready to inline. */
export const APPEARANCE_BOOT_SCRIPT = `(function(){${APPEARANCE_BOOT_SOURCE}})();`;
