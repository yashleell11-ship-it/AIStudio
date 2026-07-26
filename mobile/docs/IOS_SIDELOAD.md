# Running ManhwaManiacs on iPhone (free, no Mac)

Building an iOS binary requires macOS; installing one normally requires a $99/yr
Apple Developer account. This project needs neither:

- **Build** — GitHub Actions' free macOS runner produces an unsigned `.ipa`
  (`.github/workflows/ios-build.yml`).
- **Publish** — `ops/fetch-ios-build.sh` pulls that `.ipa` onto the NAS, and the
  backend lists it in a SideStore source at `/app/source.json`.
- **Install** — SideStore on the phone signs it with a **free** Apple ID.

Once set up, shipping a new iOS build is: push code → wait ~5 min → tap
**Update** on the phone.

> Codemagic (`codemagic.yaml`) was the original plan and still works as a
> fallback, but GitHub Actions is what's wired up and in use.

---

## One-time phone setup

Done from a **Windows** PC. (Linux is possible via the containerised `altcon`
route in SideStore's docs, but it's substantially more work — use Windows if you
have it.)

**Prerequisites:** iPhone on iOS 15+ **with a passcode set**, on WiFi, and an
Apple ID. Prefer a *throwaway* Apple ID — SideStore stores these credentials, and
the free-tier 3-app limit and 7-day certificates are charged against whichever
account signs. Never sign that account into **Settings → Media & Purchases** on
the phone, or iOS associates the device with it for 90 days.

1. **iPhone:** App Store → install **LocalDevVPN** → open it → turn the tunnel
   **on**. SideStore cannot install or refresh anything without this running.
2. **PC:** install **iTunes** (Apple's site or Microsoft Store) and launch it
   once, so its USB drivers register. Disable auto-sync:
   *Edit → Preferences → Devices → Prevent … from syncing automatically.*
3. **PC:** install **iloader** — `iloader-windows-x64.msi` from
   <https://iloader.app>. This replaced the old AltServer flow; it also places
   the pairing file, so there's no JitterbugPair step any more.
4. Plug the iPhone in, **unlock it**, tap **Trust**, enter the passcode.
5. In iloader: sign in with the Apple ID → select the device → **SideStore
   (Stable)**. (The *LiveContainer + SideStore* bundle saves an app slot but
   isn't needed — LocalDevVPN comes from the App Store and doesn't consume one.)
6. **iPhone:** *Settings → Privacy & Security → Developer Mode* → on → restart.
   **After the reboot, confirm the lock-screen prompt** — missing that leaves
   Developer Mode off.
7. **iPhone:** *Settings → General → VPN & Device Management* → **Trust** the
   developer profile. SideStore won't launch until you do.
8. Open SideStore and refresh to complete registration.

## Add the update source

In SideStore: **Browse → Sources → +** and add:

```
https://app.manhwamaniacs.xyz/app/source.json
```

ManhwaManiacs now appears in SideStore. Install it from there; future updates
are an in-app **Update** button, with no PC involved.

---

## Shipping a new iOS build

1. **Bump `version:` in `mobile/pubspec.yaml`.** This is not optional —
   SideStore compares `version`/`buildVersion` against what's installed, and both
   come from the pubspec. New code without a version bump will *not* surface an
   update, even though the served `.ipa` changed.
2. Push to the branch in `ios-build.yml` (`feat/profile-isolation-eclipse-warm`).
   Actions builds automatically, ~4–5 min.
3. Publish it on the NAS:
   ```bash
   ops/fetch-ios-build.sh
   ```
   Needs a GitHub token with **Actions: read** on the repo (the repo is private),
   from `$GH_TOKEN` or `~/.gh_token`. It no-ops (exit 2) when the newest run is
   already published, so it's safe to run on a timer:
   ```
   */10 * * * * /apps/dev/aistudio/ops/fetch-ios-build.sh >/dev/null 2>&1
   ```
4. On the phone: SideStore shows an update. Tap it.

iOS won't allow a fully silent install — that final tap is an OS-level consent
requirement, not a limitation of this setup.

### Day-to-day development

Use **Android** with hot reload for UI and logic work — it's the same Dart code
and the feedback loop is instant. Cut an iOS build when you want to verify on the
phone or ship, not for every change.

---

## How the pieces fit

| Piece | Where | Does what |
|---|---|---|
| `.github/workflows/ios-build.yml` | GitHub Actions (macOS) | Builds the unsigned `.ipa`, bakes in `FLAVOR=prod` + `API_URL` |
| `ops/fetch-ios-build.sh` | NAS | Downloads the newest successful run's artifact into `$DIR/ipa` |
| `MM_IPA_PATH` / `./ipa:/app/ipa:ro` | docker-compose | Mounts that drop read-only into the backend |
| `GET /app/source.json` | backend | SideStore source manifest (version, size, download URL) |
| `GET /app/ios/download` | backend | Serves the `.ipa` itself |
| `MM_PUBLIC_BASE_URL` | deploy `.env` | Origin for the manifest's absolute URLs — the *phone* fetches these |

The build command must carry the same dart-defines as the production APK:

```
--dart-define=FLAVOR=prod --dart-define=API_URL=https://app.manhwamaniacs.xyz
```

Without them the app falls back to `FLAVOR=dev` + `http://127.0.0.1:8000`, which
on a phone points at nothing, forces the manual setup screen, and permits a
clear-text bearer token.

## Living with a free Apple ID

- **Apps expire after 7 days.** SideStore background-refreshes over WiFi with
  LocalDevVPN on, so this is usually invisible. If it lapses, reinstall from
  SideStore — it re-signs; your data survives.
- **3 sideloaded apps max** per Apple ID. App Store apps (LocalDevVPN) don't
  count; SideStore itself does.
- App won't appear in Spotlight until first launched.
- Upgrade path if the 7-day cycle ever grates: a $99/yr Apple Developer account
  plus TestFlight, reusing this exact build — swap `--no-codesign` for a signed
  `flutter build ipa` and publish to App Store Connect.

## Troubleshooting

| Symptom | Fix |
|---|---|
| App shows the server-setup screen | dart-defines missing from the build — check the `flutter build ios` step |
| SideStore offers no update | `version:` in `mobile/pubspec.yaml` wasn't bumped |
| `/app/source.json` versions list is empty | No `.ipa` published — run `ops/fetch-ios-build.sh` |
| Manifest URLs point at an internal host | `MM_PUBLIC_BASE_URL` unset in the deploy `.env` |
| Install hangs in SideStore | Change the **anisette server** in iloader, or reinstall SideStore |
| Phone missing from iloader | Trust prompt didn't stick — unplug, replug, unlock, retry |

Docs: <https://docs.sidestore.io> · iloader: <https://github.com/nab138/iloader>
