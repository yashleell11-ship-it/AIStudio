# AIStudio Mobile — Release Build

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

## App identity

- Version: `pubspec.yaml` (`version: 1.0.0+1`)
- About screen: Settings → About (version, build, licenses)
- Launcher icon / splash: configure in generated `android/` project after `flutter create`

## Server URL

Runtime server URL is stored in secure storage and applied immediately from Settings without an app restart.

First launch shows the setup screen until a validated server URL is saved.
