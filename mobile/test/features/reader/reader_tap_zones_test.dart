import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/storage/preferences.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_tap_zones.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _tapZonesKey = 'settings_reader_tap_zones';
const _readingDirectionKey = 'settings_reading_direction';

Future<ProviderContainer> _container([
  Map<String, Object> values = const {},
]) async {
  SharedPreferences.setMockInitialValues(values);
  final prefs = await SharedPreferences.getInstance();
  return ProviderContainer(
    overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
  );
}

/// A left-handed reader's bands: the thumb that falls on the left edge is the
/// one that should turn forward.
const _leftHanded = TapZoneConfig(
  left: TapZoneAction.advance,
  center: TapZoneAction.toggle,
  right: TapZoneAction.retreat,
);

void main() {
  group('TapZoneConfig.defaultFor', () {
    test('turns the page on the outer bands and reveals chrome in the middle',
        () {
      for (final direction in [
        ReadingDirection.vertical,
        ReadingDirection.leftToRight,
      ]) {
        final zones = TapZoneConfig.defaultFor(direction);
        expect(zones.left, TapZoneAction.retreat, reason: direction.name);
        expect(zones.center, TapZoneAction.toggle, reason: direction.name);
        expect(zones.right, TapZoneAction.advance, reason: direction.name);
      }
    });

    test('mirrors the page turns for a right-to-left series', () {
      final zones = TapZoneConfig.defaultFor(ReadingDirection.rightToLeft);
      expect(zones.left, TapZoneAction.advance);
      expect(zones.center, TapZoneAction.toggle);
      expect(zones.right, TapZoneAction.retreat);
    });
  });

  group('TapZoneConfig storage', () {
    test('round-trips through its wire string', () {
      expect(_leftHanded.storageValue, 'advance,toggle,retreat');
      expect(
        TapZoneConfig.fromStorageValue(_leftHanded.storageValue)?.storageValue,
        _leftHanded.storageValue,
      );
    });

    test('reads nothing back from an absent or unusable value', () {
      expect(TapZoneConfig.fromStorageValue(null), isNull);
      expect(TapZoneConfig.fromStorageValue(''), isNull);
      expect(TapZoneConfig.fromStorageValue('advance,toggle'), isNull);
      expect(
        TapZoneConfig.fromStorageValue('advance,toggle,retreat,advance'),
        isNull,
      );
      expect(TapZoneConfig.fromStorageValue('advance,toggle,sideways'), isNull);
    });

    test('copyWith replaces one band and leaves the others alone', () {
      final zones = _leftHanded.copyWith(center: TapZoneAction.advance);
      expect(zones.storageValue, 'advance,advance,retreat');
    });
  });

  group('tapZonePositionAt', () {
    test('splits the page into thirds', () {
      expect(tapZonePositionAt(10, 300), TapZonePosition.left);
      expect(tapZonePositionAt(150, 300), TapZonePosition.center);
      expect(tapZonePositionAt(290, 300), TapZonePosition.right);
    });

    test('the band boundaries themselves belong to the centre', () {
      expect(tapZonePositionAt(100, 300), TapZonePosition.center);
      expect(tapZonePositionAt(200, 300), TapZonePosition.center);
    });

    test('honours a narrower edge band', () {
      expect(
        tapZonePositionAt(80, 300, edgeRatio: 0.1),
        TapZonePosition.center,
      );
      expect(tapZonePositionAt(20, 300, edgeRatio: 0.1), TapZonePosition.left);
    });

    test('an unmeasured page resolves to the centre', () {
      expect(tapZonePositionAt(10, 0), TapZonePosition.center);
      expect(tapZonePositionAt(10, -300), TapZonePosition.center);
    });

    test('a tap outside the page resolves to the centre', () {
      expect(tapZonePositionAt(-10, 300), TapZonePosition.center);
      expect(tapZonePositionAt(310, 300), TapZonePosition.center);
    });
  });

  group('resolveTapZone', () {
    test('applies the default bands of a left-to-right series', () {
      final zones = TapZoneConfig.defaultFor(ReadingDirection.leftToRight);
      expect(resolveTapZone(10, 300, zones), TapZoneAction.retreat);
      expect(resolveTapZone(150, 300, zones), TapZoneAction.toggle);
      expect(resolveTapZone(290, 300, zones), TapZoneAction.advance);
    });

    test('a left-handed configuration turns forward on the left edge', () {
      expect(resolveTapZone(10, 300, _leftHanded), TapZoneAction.advance);
      expect(resolveTapZone(290, 300, _leftHanded), TapZoneAction.retreat);
    });

    test('every band can be made to do the same thing', () {
      const allToggle = TapZoneConfig(
        left: TapZoneAction.toggle,
        center: TapZoneAction.toggle,
        right: TapZoneAction.toggle,
      );
      expect(resolveTapZone(10, 300, allToggle), TapZoneAction.toggle);
      expect(resolveTapZone(150, 300, allToggle), TapZoneAction.toggle);
      expect(resolveTapZone(290, 300, allToggle), TapZoneAction.toggle);
    });
  });

  group('readerDefaultsProvider tap zones', () {
    test('starts uncustomised so the bands follow the reading direction',
        () async {
      final container = await _container({
        _readingDirectionKey: ReadingDirection.rightToLeft.name,
      });
      addTearDown(container.dispose);

      final defaults = container.read(readerDefaultsProvider);
      expect(defaults.tapZones, isNull);
      expect(
        TapZoneConfig.defaultFor(defaults.direction).left,
        TapZoneAction.advance,
      );
    });

    test('persists a chosen configuration', () async {
      final container = await _container();
      addTearDown(container.dispose);

      await container
          .read(readerDefaultsProvider.notifier)
          .setTapZones(_leftHanded);

      expect(
        container.read(readerDefaultsProvider).tapZones?.storageValue,
        'advance,toggle,retreat',
      );
      expect(
        container.read(preferencesProvider).readerTapZones,
        'advance,toggle,retreat',
      );
    });

    test('reads a stored configuration on build', () async {
      final container = await _container({
        _tapZonesKey: 'advance,toggle,retreat',
      });
      addTearDown(container.dispose);

      expect(
        container.read(readerDefaultsProvider).tapZones?.storageValue,
        'advance,toggle,retreat',
      );
    });

    test('a stored value that cannot be read leaves the bands uncustomised',
        () async {
      final container = await _container({_tapZonesKey: 'nonsense'});
      addTearDown(container.dispose);

      expect(container.read(readerDefaultsProvider).tapZones, isNull);
    });

    test('resetting removes the stored value rather than freezing a default',
        () async {
      final container = await _container({
        _tapZonesKey: 'advance,toggle,retreat',
      });
      addTearDown(container.dispose);

      await container.read(readerDefaultsProvider.notifier).setTapZones(null);

      expect(container.read(readerDefaultsProvider).tapZones, isNull);
      expect(container.read(preferencesProvider).readerTapZones, isNull);
    });
  });

  group('PreferencesService tap zones', () {
    test('resetting the reader settings clears the customised bands', () async {
      SharedPreferences.setMockInitialValues({
        _tapZonesKey: 'advance,toggle,retreat',
      });
      final service = PreferencesService(await SharedPreferences.getInstance());
      expect(service.readerTapZones, 'advance,toggle,retreat');

      await service.resetReaderPreferences();

      expect(service.readerTapZones, isNull);
    });
  });
}
