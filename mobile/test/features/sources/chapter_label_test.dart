import 'package:aistudio_mobile/features/sources/utils/chapter_label.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('chapterLabel', () {
    test('leads with the canonical chapter number, title beneath', () {
      final label = chapterLabel(number: 134, title: 'The Culprit (7)');
      expect(label.primary, 'Chapter 134');
      expect(label.secondary, 'The Culprit (7)');
    });

    test('does not repeat the backend "Chapter N" fallback title', () {
      final label = chapterLabel(number: 133, title: 'Chapter 133');
      expect(label.primary, 'Chapter 133');
      expect(label.secondary, isNull);
    });

    test('formats whole numbers without a decimal point', () {
      expect(chapterLabel(number: 134.0, title: null).primary, 'Chapter 134');
      expect(chapterLabel(number: 10.5, title: null).primary, 'Chapter 10.5');
    });

    test('strips a redundant "Chapter N" prefix from titles', () {
      expect(
        chapterLabel(number: 12, title: 'Chapter 12: The Hunt').secondary,
        'The Hunt',
      );
      expect(
        chapterLabel(number: 12, title: 'chapter 12 - The Hunt').secondary,
        'The Hunt',
      );
      // A decimal continuation is a different chapter, not a redundant prefix.
      expect(
        chapterLabel(number: 12, title: 'Chapter 12.5 Special').secondary,
        'Chapter 12.5 Special',
      );
      expect(
        chapterLabel(number: 12, title: 'Chapter 125').secondary,
        'Chapter 125',
      );
    });

    test('treats empty titles as number-only chapters', () {
      expect(chapterLabel(number: 12, title: '').secondary, isNull);
      expect(chapterLabel(number: 12, title: '   ').secondary, isNull);
      expect(chapterLabel(number: 12, title: null).secondary, isNull);
    });

    test('falls back to the title only when the number is missing', () {
      final label = chapterLabel(number: null, title: 'Oneshot');
      expect(label.primary, 'Oneshot');
      expect(label.secondary, isNull);

      expect(chapterLabel(number: null, title: '').primary, 'Chapter');
    });
  });
}
