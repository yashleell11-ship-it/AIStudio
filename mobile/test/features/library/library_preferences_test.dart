import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/utils/library_preferences.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('library preferences', () {
    test('round-trips sort and filter', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      const query = LibraryQuery(
        sort: LibrarySort.dateAdded,
        filter: LibraryFilter.completed,
        viewMode: LibraryViewMode.list,
      );

      await writeLibraryQuery(prefs, query);
      final restored = readLibraryQuery(prefs);

      expect(restored.sort, LibrarySort.dateAdded);
      expect(restored.filter, LibraryFilter.completed);
      expect(restored.viewMode, LibraryViewMode.list);
    });

    test('migrates legacy unread filter to all', () async {
      SharedPreferences.setMockInitialValues({
        libraryQueryPrefsKey:
            '{"sort":"recent","filter":"unread","favoritesOnly":false,"viewMode":"grid"}',
      });
      final prefs = await SharedPreferences.getInstance();

      expect(readLibraryQuery(prefs).filter, LibraryFilter.all);
    });

    test('libraryQueryPersistedFieldsChanged ignores search-only changes', () {
      const base = LibraryQuery();
      const withSearch = LibraryQuery(search: 'solo');

      expect(libraryQueryPersistedFieldsChanged(base, withSearch), isFalse);
      expect(
        libraryQueryPersistedFieldsChanged(
          base,
          const LibraryQuery(sort: LibrarySort.dateAdded),
        ),
        isTrue,
      );
      expect(
        libraryQueryPersistedFieldsChanged(
          base,
          const LibraryQuery(filter: LibraryFilter.completed),
        ),
        isTrue,
      );
    });
  });
}
