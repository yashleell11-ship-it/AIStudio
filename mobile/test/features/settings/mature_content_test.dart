import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/repositories/mature_settings_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Profile _profile(int id) => Profile(
      id: id,
      name: 'P$id',
      avatarKey: 'violet',
      mood: Mood.neutral,
      sortOrder: 0,
      matureContentEnabled: false,
      createdAt: DateTime.utc(2024),
    );

/// In-memory `/settings` backend. Serves whatever [value] currently holds, so a
/// test can flip it to emulate a *different* profile being in scope on the next
/// read.
class _FakeMatureRepo implements MatureSettingsRepository {
  _FakeMatureRepo(this.value);

  bool value;
  bool failWrite = false;
  int getCalls = 0;

  @override
  Future<Result<bool>> getMatureEnabled() async {
    getCalls++;
    return Ok(value);
  }

  @override
  Future<Result<bool>> setMatureEnabled(bool enabled) async {
    if (failWrite) {
      return const Err(
        ApiError(statusCode: 500, code: 'server_error', message: 'nope'),
      );
    }
    value = enabled;
    return Ok(value);
  }
}

Future<ProviderContainer> _container(_FakeMatureRepo repo) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final container = ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      matureSettingsRepositoryProvider.overrideWithValue(repo),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('MatureContentController', () {
    test('build reads the flag from GET /settings', () async {
      final container = await _container(_FakeMatureRepo(true));
      expect(await container.read(matureContentProvider.future), isTrue);
    });

    test('setEnabled optimistically flips then persists via PUT /settings',
        () async {
      final repo = _FakeMatureRepo(false);
      final container = await _container(repo);
      await container.read(matureContentProvider.future);

      final error = await container
          .read(matureContentProvider.notifier)
          .setEnabled(true);

      expect(error, isNull);
      expect(repo.value, isTrue);
      expect(container.read(matureContentProvider).valueOrNull, isTrue);
    });

    test('setEnabled rolls back and returns the error on a failed write',
        () async {
      final repo = _FakeMatureRepo(false)..failWrite = true;
      final container = await _container(repo);
      await container.read(matureContentProvider.future);

      final error = await container
          .read(matureContentProvider.notifier)
          .setEnabled(true);

      expect(error, isA<ApiError>());
      // Rolled back to the pre-toggle value; the failed write left no state.
      expect(container.read(matureContentProvider).valueOrNull, isFalse);
      expect(repo.value, isFalse);
    });
  });

  group('per-profile isolation', () {
    test('switching the active profile refetches its own mature value',
        () async {
      final repo = _FakeMatureRepo(false);
      final container = await _container(repo);
      // Keep the autoDispose provider alive across the switch.
      final sub = container.listen(matureContentProvider, (_, __) {});
      addTearDown(sub.close);

      // Profile A reports 18+ off.
      expect(await container.read(matureContentProvider.future), isFalse);

      // Adopt profile A (first selection — nothing stale to invalidate).
      await container.read(activeProfileProvider.notifier).select(_profile(1));

      // The backend now reports the *other* profile's value.
      repo.value = true;

      // Switching to profile B must drop the cached value and refetch.
      await container.read(activeProfileProvider.notifier).select(_profile(2));

      expect(await container.read(matureContentProvider.future), isTrue);
      expect(repo.getCalls, greaterThanOrEqualTo(2));
    });
  });
}
