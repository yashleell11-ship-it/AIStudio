import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

class SettingsActions {
  SettingsActions(this.ref);

  final Ref ref;

  Future<AppError?> saveApiUrl(String url) async {
    final trimmed = url.trim();
    if (trimmed.isEmpty) {
      return UnknownError(message: 'Server URL cannot be empty.');
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
}

final settingsActionsProvider = Provider<SettingsActions>(
  SettingsActions.new,
  name: 'settingsActions',
);
