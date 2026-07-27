import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/auth/providers/session_offline_provider.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/repositories/profiles_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

Profile _profile({
  required int id,
  String name = 'Reader',
  String? avatarKey = 'violet',
  Mood mood = Mood.romantic,
  int sortOrder = 0,
}) =>
    Profile(
      id: id,
      name: name,
      avatarKey: avatarKey,
      mood: mood,
      sortOrder: sortOrder,
      createdAt: DateTime.utc(2024),
    );

/// In-memory repository that records calls and serves a mutable profile list.
class _FakeProfilesRepository implements ProfilesRepository {
  _FakeProfilesRepository(this.profiles);

  List<Profile> profiles;
  int nextId = 100;
  final List<String> calls = [];

  @override
  Future<Result<List<Profile>>> list() async {
    calls.add('list');
    return Ok(List.of(profiles));
  }

  @override
  Future<Result<Profile>> create({
    required String name,
    required String avatarKey,
    required Mood mood,
    int? sortOrder,
  }) async {
    calls.add('create');
    final created = _profile(
      id: nextId++,
      name: name,
      avatarKey: avatarKey,
      mood: mood,
      sortOrder: sortOrder ?? profiles.length,
    );
    profiles = [...profiles, created];
    return Ok(created);
  }

  @override
  Future<Result<Profile>> update(
    int id, {
    String? name,
    String? avatarKey,
    Mood? mood,
    int? sortOrder,
  }) async {
    calls.add('update');
    final updated = _profile(
      id: id,
      name: name ?? 'Reader',
      avatarKey: avatarKey,
      mood: mood ?? Mood.neutral,
    );
    profiles = [
      for (final p in profiles) p.id == id ? updated : p,
    ];
    return Ok(updated);
  }

  @override
  Future<Result<void>> remove(int id) async {
    calls.add('remove');
    profiles = [
      for (final p in profiles) if (p.id != id) p,
    ];
    return const Ok(null);
  }
}

Future<ProviderContainer> _container({
  required _FakeProfilesRepository repo,
  Map<String, Object> prefs = const {},
}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final instance = await SharedPreferences.getInstance();
  return ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(instance),
      profilesRepositoryProvider.overrideWithValue(repo),
    ],
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Mood', () {
    test('wire values round-trip through fromWire', () {
      for (final mood in Mood.values) {
        expect(Mood.fromWire(mood.wire), mood);
      }
    });

    test('neutral serialises as "default" and slice_of_life is snake_case', () {
      expect(Mood.neutral.wire, 'default');
      expect(Mood.sliceOfLife.wire, 'slice_of_life');
      expect(Mood.fromWire('nonsense'), Mood.neutral);
    });
  });

  group('Profile', () {
    test('fromJson maps the backend contract and snapshots losslessly', () {
      final profile = Profile.fromJson({
        'id': 7,
        'name': 'Late night',
        'avatar_key': 'horror',
        'mood': 'horror',
        'sort_order': 3,
        'created_at': '2024-01-02T03:04:05Z',
      });
      expect(profile.id, 7);
      expect(profile.mood, Mood.horror);
      expect(profile.sortOrder, 3);

      final snap = profile.toSnapshot();
      final restored = ActiveProfile.fromJson(snap.toJson());
      expect(restored.id, 7);
      expect(restored.mood, Mood.horror);
      expect(restored.name, 'Late night');
    });
  });

  group('ActiveProfileNotifier', () {
    test('select persists the snapshot and clear removes it', () async {
      final repo = _FakeProfilesRepository([]);
      final container = await _container(repo: repo);
      addTearDown(container.dispose);

      expect(container.read(activeProfileProvider), isNull);

      await container
          .read(activeProfileProvider.notifier)
          .select(_profile(id: 1, name: 'Me', mood: Mood.fantasy));
      expect(container.read(activeProfileProvider)?.id, 1);
      expect(container.read(activeProfileProvider)?.mood, Mood.fantasy);

      // A fresh container reading the same prefs restores the selection.
      final restored = await _container(
        repo: repo,
        prefs: {
          'mm.active_profile':
              '{"id":1,"name":"Me","avatar_key":"violet","mood":"fantasy"}',
        },
      );
      addTearDown(restored.dispose);
      expect(restored.read(activeProfileProvider)?.id, 1);

      await container.read(activeProfileProvider.notifier).clear();
      expect(container.read(activeProfileProvider), isNull);
    });

    test('reconcile drops the selection when the profile is gone', () async {
      final repo = _FakeProfilesRepository([]);
      final container = await _container(
        repo: repo,
        prefs: {
          'mm.active_profile':
              '{"id":9,"name":"Ghost","avatar_key":null,"mood":"default"}',
        },
      );
      addTearDown(container.dispose);
      expect(container.read(activeProfileProvider)?.id, 9);

      await container
          .read(activeProfileProvider.notifier)
          .reconcile([_profile(id: 1)]);
      expect(container.read(activeProfileProvider), isNull);
    });
  });

  group('ProfilesNotifier', () {
    test('build returns profiles sorted by sort_order', () async {
      final repo = _FakeProfilesRepository([
        _profile(id: 1, sortOrder: 2),
        _profile(id: 2),
        _profile(id: 3, sortOrder: 1),
      ]);
      final container = await _container(repo: repo);
      addTearDown(container.dispose);

      final list = await container.read(profilesProvider.future);
      expect(list.map((p) => p.id), [2, 3, 1]);
    });

    test('create then refresh surfaces the new profile', () async {
      final repo = _FakeProfilesRepository([_profile(id: 1)]);
      final container = await _container(repo: repo);
      addTearDown(container.dispose);
      await container.read(profilesProvider.future);

      final error = await container.read(profilesProvider.notifier).create(
            name: 'Weekend',
            avatarKey: 'amber',
            mood: Mood.comedy,
          );
      expect(error, isNull);
      expect(repo.calls, contains('create'));
      final list = await container.read(profilesProvider.future);
      expect(list.any((p) => p.name == 'Weekend'), isTrue);
    });

    test('deleting the active profile clears the selection', () async {
      final repo = _FakeProfilesRepository([_profile(id: 1, name: 'Solo')]);
      final container = await _container(repo: repo);
      addTearDown(container.dispose);
      await container.read(profilesProvider.future);

      await container
          .read(activeProfileProvider.notifier)
          .select(_profile(id: 1, name: 'Solo'));
      expect(container.read(activeProfileProvider)?.id, 1);

      final error = await container.read(profilesProvider.notifier).delete(1);
      expect(error, isNull);
      expect(container.read(activeProfileProvider), isNull);
    });

    test('a repository error is returned, not thrown', () async {
      final repo = _ErroringRepository();
      final container = await _container(repo: repo);
      addTearDown(container.dispose);

      final error = await container.read(profilesProvider.notifier).create(
            name: 'X',
            avatarKey: 'violet',
            mood: Mood.neutral,
          );
      expect(error, isA<ApiError>());
    });
  });

  group('ProfileSessionReadyNotifier', () {
    const persisted = {
      'mm.active_profile':
          '{"id":1,"name":"Me","avatar_key":"violet","mood":"fantasy"}',
    };

    test('the gate stands on a normal cold start', () async {
      final container = await _container(
        repo: _FakeProfilesRepository([]),
        prefs: persisted,
      );
      addTearDown(container.dispose);

      expect(container.read(profileSessionReadyProvider), isFalse);
    });

    test('an offline session enters on the persisted profile', () async {
      final container = await _container(
        repo: _FakeProfilesRepository([]),
        prefs: persisted,
      );
      addTearDown(container.dispose);
      expect(container.read(profileSessionReadyProvider), isFalse);

      // The picker cannot list profiles with the server down, so gating on it
      // would park the user on a screen with no tiles and no way forward.
      container.read(sessionOfflineProvider.notifier).markOffline();
      expect(container.read(profileSessionReadyProvider), isTrue);
    });

    test('an offline session with nothing persisted still shows the picker',
        () async {
      final container = await _container(repo: _FakeProfilesRepository([]));
      addTearDown(container.dispose);

      container.read(sessionOfflineProvider.notifier).markOffline();
      expect(container.read(profileSessionReadyProvider), isFalse);
    });
  });
}

class _ErroringRepository extends _FakeProfilesRepository {
  _ErroringRepository() : super([]);

  @override
  Future<Result<Profile>> create({
    required String name,
    required String avatarKey,
    required Mood mood,
    int? sortOrder,
  }) async =>
      const Err(
        ApiError(statusCode: 409, code: 'limit', message: 'Too many profiles'),
      );
}
