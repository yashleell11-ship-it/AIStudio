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
