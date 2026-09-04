import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_preferences_provider.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_chapter_view.dart';

/// The novel reader's reading palettes and prose typography are a **third**
/// axis, independent of both the app theme and the design preset.
///
/// A design preset changes the app's chrome — density, corner radius, surface
/// treatment, the UI type scale. It must not reach into the page a novel is
/// set on: that surface is chosen by the reader in the reader's own settings,
/// its size is theirs, and a preset quietly shrinking their prose (or repainting
/// their sepia page) would be the design system overstepping into a setting the
/// reader already made deliberately.
void main() {
  const paragraphs = ['The first paragraph.', 'And a second one after it.'];
  const surface = NovelSurfaceColors(
    bg: Color(0xFFFBF0D9),
    ink: Color(0xFF3B3128),
    muted: Color(0xFF6B5C4A),
    isDark: false,
  );

  Future<TextStyle> proseStyleUnder(
    WidgetTester tester, {
    required String presetId,
    required String paletteId,
    required NovelPreferences preferences,
  }) async {
    final keys = [GlobalKey(), GlobalKey()];
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.fromPalette(
          AppPalettes.byId(paletteId),
          metrics: AppPresets.byId(presetId),
        ),
        home: Scaffold(
          body: CustomScrollView(
            slivers: [
              NovelChapterView(
                paragraphs: paragraphs,
                palette: surface,
                preferences: preferences,
                paragraphKeys: keys,
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    // The second paragraph carries no drop cap, so its Text.rich style is the
    // prose style with nothing layered on top. Found by the paragraph's own
    // key rather than by its text, which lives in a span.
    final text = tester.widget<Text>(
      find.descendant(of: find.byKey(keys[1]), matching: find.byType(Text)),
    );
    return text.style!;
  }

  testWidgets('prose keeps the reader\'s size and ink under every preset',
      (tester) async {
    // Deliberately not the defaults: the point is that a choice the reader
    // made survives every preset.
    const preferences = NovelPreferences(fontSize: 21, lineHeight: 1.85);

    TextStyle? first;
    for (final preset in AppPresets.all) {
      final style = await proseStyleUnder(
        tester,
        presetId: preset.id,
        paletteId: 'eclipse',
        preferences: preferences,
      );
      expect(style.fontSize, preferences.fontSize, reason: preset.id);
      expect(style.height, preferences.lineHeight, reason: preset.id);
      expect(style.color, surface.ink, reason: preset.id);
      expect(style.fontFamily, kNovelSerifStack.first, reason: preset.id);
      // Not merely "within tolerance" — identical, preset to preset.
      first ??= style;
      expect(style, first, reason: preset.id);
    }
  });

  testWidgets('the app palette does not repaint the reading surface either',
      (tester) async {
    const preferences = NovelPreferences(
      fontSize: 17,
      lineHeight: 1.6,
      fontFamily: NovelFontFamily.sans,
    );

    for (final paletteId in ['eclipse', 'nord', 'paper', 'solarized_light']) {
      final style = await proseStyleUnder(
        tester,
        presetId: 'cinema',
        paletteId: paletteId,
        preferences: preferences,
      );
      expect(style.color, surface.ink, reason: paletteId);
      expect(style.fontSize, preferences.fontSize, reason: paletteId);
      expect(style.fontFamily, kNovelSansStack.first, reason: paletteId);
    }
  });
}
