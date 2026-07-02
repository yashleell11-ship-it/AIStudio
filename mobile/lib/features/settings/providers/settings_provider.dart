import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/library/providers/bookmarks_provider.dart';
import 'package:aistudio_mobile/features/library/providers/dashboard_providers.dart';
import 'package:aistudio_mobile/features/library/providers/intelligence_providers.dart';
import 'package:aistudio_mobile/features/library/providers/library_list_provider.dart';
import 'package:aistudio_mobile/features/settings/models/reader_defaults.dart';
import 'package:aistudio_mobile/features/settings/services/image_cache_service.dart';
import 'package:aistudio_mobile/features/updates/providers/updates_provider.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

final downloadSettingsProvider =
    FutureProvider.autoDispose<DownloadSettings>((ref) async {
  final repo = ref.watch(downloadsRepositoryProvider);
  final result = await repo.getSettings();
  if (result.isErr) throw result.error;
  return result.value;
});

final settingsApiUrlProvider = FutureProvider.autoDispose<String>((ref) async {
  final storage = ref.watch(secureStorageProvider);
  final saved = await storage.getApiUrl();
  return saved ?? ref.watch(apiBaseUrlProvider);
});

// ── Theme ────────────────────────────────────────────────────────────────

class ThemeModeController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => ref.watch(preferencesProvider).themeMode;

  Future<void> setThemeMode(ThemeMode mode) async {
    state = mode;
    await ref.read(preferencesProvider).setThemeMode(mode);
  }
}

final themeModeProvider =
    NotifierProvider<ThemeModeController, ThemeMode>(ThemeModeController.new);

// ── Language ─────────────────────────────────────────────────────────────

class LanguageController extends Notifier<AppLanguage> {
  @override
  AppLanguage build() => AppLanguage.fromCode(ref.watch(preferencesProvider).language);

  Future<void> setLanguage(AppLanguage language) async {
    state = language;
    await ref.read(preferencesProvider).setLanguage(language.code);
  }
}

final languageProvider =
    NotifierProvider<LanguageController, AppLanguage>(LanguageController.new);

// ── Reader defaults ──────────────────────────────────────────────────────

class ReaderDefaultsController extends Notifier<ReaderDefaults> {
  @override
  ReaderDefaults build() {
    final prefs = ref.watch(preferencesProvider);
    return ReaderDefaults(
      direction: ReadingDirection.fromStorageValue(prefs.readingDirection),
      fitMode: ReaderFitMode.fromStorageValue(prefs.readerFitMode),
      keepScreenAwake: prefs.keepScreenAwake,
      autoNextChapter: prefs.autoNextChapter,
    );
  }

  Future<void> setDirection(ReadingDirection direction) async {
    state = state.copyWith(direction: direction);
    await ref.read(preferencesProvider).setReadingDirection(direction.name);
  }

  Future<void> setFitMode(ReaderFitMode fitMode) async {
    state = state.copyWith(fitMode: fitMode);
    await ref.read(preferencesProvider).setReaderFitMode(fitMode.name);
  }

  Future<void> setKeepScreenAwake(bool value) async {
    state = state.copyWith(keepScreenAwake: value);
    await ref.read(preferencesProvider).setKeepScreenAwake(value);
  }

  Future<void> setAutoNextChapter(bool value) async {
    state = state.copyWith(autoNextChapter: value);
    await ref.read(preferencesProvider).setAutoNextChapter(value);
  }
}

final readerDefaultsProvider =
    NotifierProvider<ReaderDefaultsController, ReaderDefaults>(
  ReaderDefaultsController.new,
);

// ── Download preferences (client-side only; no backend field exists) ───────

class WifiOnlyDownloadsController extends Notifier<bool> {
  @override
  bool build() => ref.watch(preferencesProvider).wifiOnlyDownloads;

  Future<void> setEnabled(bool value) async {
    state = value;
    await ref.read(preferencesProvider).setWifiOnlyDownloads(value);
  }
}

final wifiOnlyDownloadsProvider =
    NotifierProvider<WifiOnlyDownloadsController, bool>(
  WifiOnlyDownloadsController.new,
);

// ── Cache ────────────────────────────────────────────────────────────────

final imageCacheServiceProvider = Provider<ImageCacheService>(
  (_) => const ImageCacheServiceImpl(),
  name: 'imageCacheService',
);

final cacheUsageProvider = FutureProvider.autoDispose<int>((ref) {
  return ref.watch(imageCacheServiceProvider).getCacheSizeBytes();
});

// ── About ────────────────────────────────────────────────────────────────

final packageInfoProvider = FutureProvider.autoDispose<PackageInfo>((ref) {
  return PackageInfo.fromPlatform();
});

// ── Actions ──────────────────────────────────────────────────────────────

class SettingsActions {
  SettingsActions(this.ref);

  final Ref ref;

  Future<AppError?> saveApiUrl(String url) async {
    final trimmed = url.trim();
    if (trimmed.isEmpty) {
      return const UnknownError(message: 'Server URL cannot be empty.');
    }
    await ref.read(secureStorageProvider).setApiUrl(trimmed);
    ref.invalidate(settingsApiUrlProvider);
    return null;
  }

  Future<void> resetApiUrl() async {
    await ref.read(secureStorageProvider).clearApiUrl();
    ref.invalidate(settingsApiUrlProvider);
  }

  Future<AppError?> saveDownloadSettings(DownloadSettings settings) async {
    final repo = ref.read(downloadsRepositoryProvider);
    final result = await repo.updateSettings(settings);
    if (result.isErr) return result.error;
    ref.invalidate(downloadSettingsProvider);
    return null;
  }

  /// Clears every cached page/cover image on disk.
  Future<void> clearImageCache() async {
    await ref.read(imageCacheServiceProvider).clear();
    ref.invalidate(cacheUsageProvider);
  }

  /// Invalidates the in-memory library/reading metadata providers so the
  /// next visit to those screens refetches from the server. There is no
  /// persistent metadata store on the client to delete from disk — this
  /// only resets Riverpod's cached state.
  void clearMetadataCache() {
    for (final invalidate in metadataCacheInvalidators) {
      invalidate(ref);
    }
  }
}

final settingsActionsProvider = Provider<SettingsActions>(
  SettingsActions.new,
  name: 'settingsActions',
);

/// Providers invalidated by [SettingsActions.clearMetadataCache], exposed
/// separately so tests can verify the exact set without invoking the whole
/// action.
///
/// Invalidates each top-level data provider directly rather than the shared
/// [libraryRepositoryProvider]: several of them (`bookmarksProvider`,
/// `libraryListProvider`) read the repository with `ref.read`, not
/// `ref.watch`, so invalidating only the repository would silently miss
/// them.
final List<void Function(Ref ref)> metadataCacheInvalidators = [
  (ref) => ref.invalidate(dashboardProvider),
  (ref) => ref.invalidate(libraryListProvider),
  (ref) => ref.invalidate(searchListProvider),
  (ref) => ref.invalidate(statisticsProvider),
  (ref) => ref.invalidate(recommendationsProvider),
  (ref) => ref.invalidate(readingHistoryProvider),
  (ref) => ref.invalidate(bookmarksProvider),
  (ref) => ref.invalidate(updatesProvider),
];
