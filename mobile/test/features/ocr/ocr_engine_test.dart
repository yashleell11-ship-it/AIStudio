import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_engine.dart';

/// The `mm/ocr` channel is the seam between Dart and two hand-written native
/// handlers that nothing in CI can execute. These tests drive the Dart half
/// against a fake handler so the decode contract — page numbering, missing
/// geometry, and a handler that returns junk — is pinned even though the
/// Swift/Kotlin halves are only ever verified on a device.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  void handle(Future<Object?>? Function(MethodCall call)? handler) {
    messenger.setMockMethodCallHandler(MethodChannelOcrEngine.channel, handler);
  }

  tearDown(() => handle(null));

  group('channel decoding', () {
    test('stamps real page numbers from startPage, not the batch index', () {
      final decoded = [
        for (var i = 0; i < 2; i++)
          PageText.fromChannel({'text': 'page $i'}, page: 7 + i),
      ];

      expect(decoded.map((p) => p.page), [7, 8]);
    });

    test('reads boxes, dropping non-numeric geometry rather than throwing', () {
      final page = PageText.fromChannel({
        'text': 'hello',
        'boxes': [
          {
            'text': 'hello',
            'x': 0.1,
            'y': 0.2,
            'width': 0.3,
            'height': 0.4,
            'confidence': 0.95,
          },
          {'text': 'no geometry', 'x': 'nonsense'},
        ],
      }, page: 1);

      expect(page.boxes, hasLength(2));
      expect(page.boxes.first.x, 0.1);
      expect(page.boxes.first.confidence, 0.95);
      expect(page.boxes.last.x, isNull);
      expect(page.boxes.last.text, 'no geometry');
    });

    test('a page with no boxes key decodes to an empty box list', () {
      expect(PageText.fromChannel({'text': 'hi'}, page: 1).boxes, isEmpty);
    });
  });

  group('MethodChannelOcrEngine on the test host', () {
    // `flutter test` reports the host platform (linux here), which is exactly
    // the "no native handler" case spec §4 says must hide the feature — so
    // these assert the *degrade*, which is the behaviour that matters.
    const engine = MethodChannelOcrEngine();

    test('isAvailable is false with no supported platform', () async {
      expect(await engine.isAvailable(), isFalse);
    });

    test('isAvailable stays false when the handler throws', () async {
      handle((_) async => throw PlatformException(code: 'boom'));

      expect(await engine.isAvailable(), isFalse);
    });

    test('engineId degrades to a sentinel instead of throwing', () async {
      expect(await engine.engineId(), 'unavailable');
    });

    test('recognize refuses rather than hanging on an unsupported host',
        () async {
      expect(() => engine.recognize(['/tmp/page.jpg']), throwsStateError);
    });

    test('an empty path list short-circuits before touching the channel',
        () async {
      expect(await engine.recognize(const []), isEmpty);
    });
  });
}
