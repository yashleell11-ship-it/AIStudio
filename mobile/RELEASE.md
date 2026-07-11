# ManhwaManiacs Mobile — Release Build

## Prerequisites

- Flutter SDK ≥ 3.22
- Android SDK (for APK)

## First-time platform setup

This repository ships the Dart application layer. Generate platform folders once:

```powershell
cd mobile
flutter create . --platforms=android
flutter pub get
```

## Release APK

```powershell
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release --dart-define=FLAVOR=prod
```

Output: `mobile/build/app/outputs/flutter-apk/app-release.apk`

### Build notes / gotchas

- **compileSdk override:** `flutter_displaymode` 0.6.0 hard-pins `compileSdkVersion 33`, but its transitive AndroidX deps require newer. `android/build.gradle.kts` has a `subprojects { afterEvaluate { … } }` block that bumps any Android module below a floor (`MIN_COMPILE_SDK`, currently 36) up to that floor. It is registered *before* the `evaluationDependsOn(":app")` block — reordering it after causes `Cannot run afterEvaluate when the project is already evaluated`. The floor was raised from 34 to 36 when `file_picker` (via `flutter_plugin_android_lifecycle`) started requiring compileSdk 36 — bump `MIN_COMPILE_SDK` again whenever a future plugin demands more (make sure the matching `platforms;android-<N>` package is installed via `sdkmanager` first).
- The release build is **debug-signed** (no `android/key.properties`). Add a keystore + `key.properties` for a Play-store-signed build.
- Benign warnings during build: KGP-migration notice (package_info_plus, wakelock_plus) and a `cupertino_icons` font tree-shaking message — neither fails the build.

## App identity

- Version: `pubspec.yaml` (`version: 1.0.0+1`)
- About screen: Settings → About (version, build, licenses)
- Launcher icon / splash: configure in generated `android/` project after `flutter create`

## Server URL

Runtime server URL is stored in secure storage and applied immediately from Settings without an app restart.

First launch shows the setup screen until a validated server URL is saved.

The **release** flavor (`--dart-define=FLAVOR=prod`) refuses a plain `http://`
base URL (the bearer token must never travel in clear text), and the compile-time
default is `http://127.0.0.1:8000`. So a production APK is always built with an
explicit HTTPS default that points at the backend it will talk to:

```
--dart-define=FLAVOR=prod --dart-define=API_URL=https://app.manhwamaniacs.xyz
```

The user can still change the server URL in Settings, but this ships a working
default so the app connects the moment it's installed.

---

# app.manhwamaniacs.xyz — phone install subdomain

A dedicated subdomain serves the latest APK so it can be installed straight from a
phone browser: open **https://app.manhwamaniacs.xyz** → **Download the app**.

## How it's wired

- **Backend serves it directly.** `backend/routes/app_distribution.py` renders the
  install/landing page (`GET /` with `Accept: text/html`) and streams the APK at
  `GET /app/download`; `GET /health` powers the live status pill. All links are
  same-origin, so the whole page works on the app subdomain with no `/api` prefix.
- **APK location.** The backend reads `MM_APK_PATH` (default `/app/apk/app-release.apk`).
  `docker-compose.yml` mounts `./apk` into the backend read-only and mounts
  `mobile/pubspec.yaml` so the version label is live.
- **Build on deploy.** `ops/deploy.sh` (`build_apk`) runs
  `flutter build apk --release --dart-define=FLAVOR=prod --dart-define=API_URL=https://app.<host>`
  after syncing the source, then copies the result into `<env-dir>/apk/`. It is
  best-effort — if the Flutter/Android toolchain is missing it warns, falls back to
  a prebuilt APK carried in the source tree, and never fails the deploy. Production
  and staging get an app subdomain (`app.` / `app.staging.`); previews don't.
- **Edge routing.** The backend also joins the `edge` Docker network, and the deploy
  writes a Caddy vhost `manhwamaniacs-production-app.caddy`
  (`app.manhwamaniacs.xyz → manhwamaniacs-production-backend:8000`). The apex
  `manhwamaniacs.xyz` still points only at the frontend.

## Build host requirement (Android toolchain)

`flutter build apk` needs a **JDK 17** and the **Android SDK** (cmdline-tools,
`platforms;android-36`, `build-tools;36.0.0`) on the deploy host. If they're absent,
install once (no root needed), e.g. under `/home/yash`:

```bash
# JDK 17
curl -sL -o jdk17.tar.gz "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
mkdir -p ~/jdk17 && tar -xzf jdk17.tar.gz -C ~/jdk17 --strip-components=1
# Android cmdline-tools + packages
curl -sL -o cmdline-tools.zip "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
mkdir -p ~/Android/Sdk/cmdline-tools && (cd ~/Android/Sdk/cmdline-tools && unzip -q ~/cmdline-tools.zip && mv cmdline-tools latest)
export JAVA_HOME=~/jdk17 ANDROID_SDK_ROOT=~/Android/Sdk
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"
```

`build_apk` auto-discovers Flutter at `/home/yash/flutter/bin`, the SDK at
`$ANDROID_SDK_ROOT`/`/home/yash/Android/Sdk`, and the JDK at `$JAVA_HOME`/`/home/yash/jdk17`.

## DNS (one-time, manual — Cloudflare)

There is **no wildcard DNS**, so each hostname needs its own record. The tunnel
already has a `*.manhwamaniacs.xyz` ingress rule, so **only a DNS record** is needed
(no cloudflared change). Add a **proxied CNAME**:

| Type  | Name  | Target                                              | Proxy |
|-------|-------|-----------------------------------------------------|-------|
| CNAME | `app` | `5835a60c-2cdc-4b02-adbc-104fec406147.cfargotunnel.com` | ✅ Proxied |

Dashboard: Cloudflare → manhwamaniacs.xyz → DNS → Add record (as above). Or CLI on
the tunnel host: `cloudflared tunnel route dns 5835a60c-2cdc-4b02-adbc-104fec406147 app.manhwamaniacs.xyz`.

## Deploy & verify

```bash
ops/deploy.sh production
# once DNS has propagated:
curl -sk https://app.manhwamaniacs.xyz/health          # {"status":"online",...}
curl -skI https://app.manhwamaniacs.xyz/app/download    # 200, Content-Type: application/vnd.android.package-archive
```

Then on the phone: open **https://app.manhwamaniacs.xyz** and tap **Download the app**.
