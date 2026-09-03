/// One run of snippet text, and whether the backend marked it as a match.
typedef OcrSnippetSpan = ({String text, bool highlighted});

/// Splits a `/ocr/search` snippet into plain/highlighted runs.
///
/// The backend wraps matched terms in `<mark>…</mark>` because it was written
/// for the web client, which renders HTML. Flutter has no HTML in a `Text`,
/// so a snippet dropped straight into one reads as literal `<mark>` tags —
/// this turns it into spans a `RichText` can style instead.
///
/// Anything that is not a well-formed `<mark>`/`</mark>` pair is kept as
/// literal text: a chapter whose dialogue genuinely contains an angle bracket
/// must show that bracket, not silently lose it.
List<OcrSnippetSpan> ocrSnippetSpans(String snippet) {
  if (snippet.isEmpty) return const [];

  final spans = <OcrSnippetSpan>[];
  final buffer = StringBuffer();
  var highlighted = false;
  var index = 0;

  void flush() {
    if (buffer.isEmpty) return;
    spans.add((text: buffer.toString(), highlighted: highlighted));
    buffer.clear();
  }

  while (index < snippet.length) {
    if (!highlighted && snippet.startsWith('<mark>', index)) {
      flush();
      highlighted = true;
      index += '<mark>'.length;
      continue;
    }
    if (highlighted && snippet.startsWith('</mark>', index)) {
      flush();
      highlighted = false;
      index += '</mark>'.length;
      continue;
    }
    buffer.write(snippet[index]);
    index++;
  }
  flush();

  return spans;
}
