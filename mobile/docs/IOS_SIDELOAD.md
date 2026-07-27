# Running ManhwaManiacs on iPhone (free, no Mac)

Building an iOS binary requires macOS; installing one normally requires a $99/yr
Apple Developer account. This project needs neither:

- **Build** — GitHub Actions' free macOS runner produces an unsigned `.ipa`
  (`.github/workflows/ios-build.yml`).
- **Publish** — a cron job on the NAS pulls that `.ipa` (`ops/fetch-ios-build.sh`)
  and the backend lists it in a SideStore source at `/app/source.json`.
- **Install** — SideStore on the phone signs it with a **free** Apple ID.

Once set up, shipping a new iOS build is: push code → wait ~10 min → tap
**Update** on the phone. Nothing to bump, download, or sideload by hand.

> Codemagic (`codemagic.yaml`) was the original plan. **Do not use it as-is** —
> its build step (`codemagic.yaml:34`) is a bare
> `flutter build ios --release --no-codesign` with no `--dart-define`, so the
> `.ipa` it produces is a *dev*-flavour app pointed at `http://127.0.0.1:8000`
> (`mobile/lib/core/config/env.dart:6-9,14-17`). GitHub Actions is what's wired
> up and in use.

> **The workflow only exists locally.** `github/feat/profile-isolation-eclipse-warm`
> is behind HEAD, and the tracking remote (`origin`) is the NAS Forgejo, not
> GitHub. Until someone runs `git push github feat/profile-isolation-eclipse-warm`
> there is no iOS build on GitHub at all, and every fix in this document is
> theoretical. Re-push after each change — Actions builds what GitHub has, not
> what your working tree has.

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

Once the sync timer is installed (see below), this is the whole loop:

1. Push to the branch in `ios-build.yml` (`feat/profile-isolation-eclipse-warm`).
   Actions builds automatically, ~4–5 min.
2. Within 10 minutes the NAS pulls the build and starts advertising it.
3. On the phone: SideStore shows an update. Tap it.

iOS won't allow a fully silent install — that final tap is an OS-level consent
requirement, not a limitation of this setup.

**Build numbers are automatic.** CI stamps `1000 + <run number>` into each
`.ipa` and writes the numbers it used into an `ios-build.json` beside it; the
server advertises *that*, not its own checkout of the pubspec. So pushing code is
enough to surface an update — no version bump needed.

`version:` in `mobile/pubspec.yaml` still controls the human-readable version
*name* (and the Android build number), so bump it when you want the phone to say
1.3.3 instead of 1.3.2. Add a matching `_RELEASE_NOTES` entry in
`backend/routes/app_distribution.py` and SideStore will show those notes on the
update.

### Installing the sync timer (one time)

The pull is a root cron job — the publish directory under `/srv/apps` is owned by
`nas`, and the script chowns the result to the container's uid.

```bash
sudo install -m 644 /apps/dev/aistudio/ops/manhwamaniacs-ios-sync.cron /etc/cron.d/manhwamaniacs-ios-sync
```

It needs a GitHub token with **Actions: read** on the repo (the repo is private)
at `/root/.gh_token`, mode 600. Without it every run fails and logs.

Runs land in `/var/log/manhwamaniacs-ios-sync.log`, but only when something
happened — a "nothing new" poll is silent. To publish immediately instead of
waiting for the timer:

```bash
sudo /apps/dev/aistudio/ops/fetch-ios-build.sh
```

### Day-to-day development

Use **Android** with hot reload for UI and logic work — it's the same Dart code
and the feedback loop is instant. Cut an iOS build when you want to verify on the
phone or ship, not for every change.

---

## How the pieces fit

| Piece | Where | Does what |
|---|---|---|
| `.github/workflows/ios-build.yml` | GitHub Actions (macOS) | Builds the unsigned `.ipa`, stamps the build number, bakes in `FLAVOR=prod` + `API_URL` |
| `ios-build.json` | beside the `.ipa` | The version/build CI put *in* that binary — the server can't read it back out of an `.ipa` |
| `/etc/cron.d/manhwamaniacs-ios-sync` | NAS | Runs the pull every 10 min via `ops/ios-sync-cron.sh` |
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

## How the iOS dependencies are pinned

Nobody on this project has a Mac, so the cloud runner has to be able to build
without a human resolving anything. Two settings make that true, and both are
load-bearing:

| Setting | Where | Why |
|---|---|---|
| `config: enable-swift-package-manager: false` | `mobile/pubspec.yaml` | Swift Package Manager is **on by default** on Flutter stable. With it on, `file_picker` resolves its iOS dependencies by cloning six repos from GitHub *at build time* — three of them tracked by a moving branch, none of them pinned by anything in this repo. It also runs *alongside* CocoaPods, because `flutter_secure_storage` ships no `Package.swift`, and Flutter warns that combination can produce duplicate-module link failures. |
| `Pod::PICKER_MEDIA = false` | `mobile/ios/Podfile` | Drops `DKImagePickerController` — the only remote pod in the project. With it gone, every pod is a local path pod and `pod install` touches the network zero times. It is also the only code that reaches `PHPhotoLibrary`. |

Net effect: the entire iOS dependency graph is pinned by `mobile/pubspec.lock`
alone. Nothing is fetched, so nothing can drift or 404 mid-build.

`mobile/ios/Podfile` is **checked in on purpose** — Flutter generates one when
it's missing and preserves it when it's there, so committing it is what makes
the two settings above survive a CI checkout.

There is no `mobile/ios/Podfile.lock` yet, because generating one requires a Mac.
The workflow uploads the one CI produces as a separate `ios-podfile-lock`
artifact: after the first green run, download it, drop it in `mobile/ios/` and
commit it. (With only path-based pods this is belt-and-braces, not a
correctness requirement.)

### Deployment target

`IPHONEOS_DEPLOYMENT_TARGET = 13.0` in every build configuration of
`Runner.xcodeproj`, `platform :ios, '13.0'` in the Podfile, and 13.0 in the
`Flutter.podspec` podhelper generates. 13.0 is also the highest floor any
dependency asks for — `url_launcher_ios` and `shared_preferences_foundation` sit
exactly on it, everything else is 12.0 or lower. Keep all three in step if you
ever raise it.

### Purpose strings

`mobile/ios/Runner/Info.plist` carries `NSPhotoLibraryUsageDescription` and
`NSAppleMusicUsageDescription`. Neither is reachable from the app's own Dart
today — the single `FilePicker.platform.pickFiles()` call
(`lib/features/settings/screens/backup_screen.dart:43`) uses the default
`FileType.any`, which is the document-picker path and needs no permission. They
are there because a missing purpose string is not a warning on iOS: it is an
immediate process kill, and on a sideloaded build that is indistinguishable from
a lapsed certificate. The build step asserts both survived into the binary.

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
| No workflow run appears at all | The branch was never pushed to `github` — `git push github feat/profile-isolation-eclipse-warm` |
| App shows the server-setup screen | dart-defines missing from the build — check the `flutter build ios` step |
| Build dies resolving Swift packages | `enable-swift-package-manager: false` was lost from `mobile/pubspec.yaml`, or `mobile/ios/Podfile` isn't in the checkout |
| Build dies cloning `DKImagePickerController` / `SDWebImage` | Same cause — see the pinning table above |
| App dies instantly when picking a file | A purpose string is missing. The **Verify** step should have caught it; check its output |
| Settings → cache size crashes | `path_provider_foundation` is an FFI/native-assets package now — look at the native-assets build output first |
| SideStore offers no update | Check `/var/log/manhwamaniacs-ios-sync.log`, then that `buildVersion` in `/app/source.json` actually went up |
| `buildVersion` didn't go up after a push | No `ios-build.json` beside the `.ipa`, so it fell back to the pubspec — check the artifact contains both files |
| `/app/source.json` versions list is empty | No `.ipa` published — run `sudo ops/fetch-ios-build.sh` |
| Manifest URLs point at an internal host | `MM_PUBLIC_BASE_URL` unset in the deploy `.env` |
| Install hangs in SideStore | Change the **anisette server** in iloader, or reinstall SideStore |
| Phone missing from iloader | Trust prompt didn't stick — unplug, replug, unlock, retry |
| `OperationError 1006` — "could not determine this device's UDID" | The pairing file is stale or gone. Nothing to do with the build — SideStore reads the UDID from that file to sign, so *every* install and refresh fails the same way until it is replaced. Turn LocalDevVPN on, plug into the PC, unlock, Trust, then re-pair in iloader. iOS invalidates pairing records on its own (an iOS update or a long gap without connecting will do it) |

Docs: <https://docs.sidestore.io> · iloader: <https://github.com/nab138/iloader>
