/// Display label for a source chapter.
///
/// The canonical chapter number always leads; the source-provided title is
/// separate metadata shown beneath it. Only when a source has no chapter
/// number does the title become the label.
class ChapterLabel {
  const ChapterLabel({required this.primary, this.secondary});

  final String primary;
  final String? secondary;
}

ChapterLabel chapterLabel({required double? number, required String? title}) {
  final trimmed = title?.trim() ?? '';
  if (number == null) {
    return ChapterLabel(primary: trimmed.isEmpty ? 'Chapter' : trimmed);
  }
  final formatted =
      number % 1 == 0 ? number.toInt().toString() : number.toString();
  final primary = 'Chapter $formatted';
  return ChapterLabel(primary: primary, secondary: _dedupeTitle(trimmed, primary));
}

/// Sources often embed the chapter number in the title ("Chapter 134", or
/// "Chapter 12: The Hunt"). The number line already shows it, so drop the
/// redundant prefix — but never a decimal continuation ("Chapter 12.5").
String? _dedupeTitle(String title, String primary) {
  if (title.isEmpty) return null;
  if (title.toLowerCase().startsWith(primary.toLowerCase())) {
    final rest = title.substring(primary.length);
    if (rest.isEmpty) return null;
    final separator = RegExp(r'^\s*[:\-–—]\s*|^\s+').firstMatch(rest);
    if (separator != null) {
      final remainder = rest.substring(separator.group(0)!.length).trim();
      return remainder.isEmpty ? null : remainder;
    }
  }
  return title;
}
