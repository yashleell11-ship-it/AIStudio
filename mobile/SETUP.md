# ManhwaManiacs Mobile — Setup

## Prerequisites

- Flutter SDK ≥ 3.22 — https://docs.flutter.dev/get-started/install
- Dart ≥ 3.4

## Verify

```powershell
flutter --version
dart --version
```

## Install dependencies

```powershell
cd mobile
flutter pub get
```

## Analyze

```powershell
flutter analyze
```

Expected: 0 errors, 0 warnings (generated files excluded via analysis_options.yaml).

## Test

```powershell
flutter test
```

Expected: all tests pass.

## Format

```powershell
dart format lib/ test/
```

## Build flavors

```powershell
# Dev (default — points to 127.0.0.1:8000)
flutter run --dart-define=FLAVOR=dev

# Custom server
flutter run --dart-define=FLAVOR=prod --dart-define=API_URL=http://192.168.1.10:8000
```

Runtime server URL can also be set from Settings → Server URL (stored in secure storage, survives restarts).

## Adding feature screens

1. Create `lib/features/<name>/` with `models/`, `repositories/`, `providers/`, `screens/`, `widgets/`
2. Register routes in `lib/app/router/app_router.dart` (replace `PlaceholderScreen`)
3. Add Riverpod providers to `lib/shared/providers/repository_providers.dart`
4. Run `dart format` + `flutter analyze` + `flutter test`

## Code generation (when using freezed / json_serializable / riverpod_generator)

```powershell
dart run build_runner build --delete-conflicting-outputs
```
