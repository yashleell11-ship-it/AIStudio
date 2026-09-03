import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_snippet.dart';

/// `/ocr/search` snippets carry `<mark>` tags because the backend was written
/// for the web client. Flutter renders none of that, so these pin the split
/// into styleable spans — including the case where a chapter's dialogue
/// legitimately contains an angle bracket.
void main() {
  test('splits a marked snippet into plain and highlighted runs', () {
    final spans = ocrSnippetSpans('I told <mark>you</mark> already');

    expect(spans, [
      (text: 'I told ', highlighted: false),
      (text: 'you', highlighted: true),
      (text: ' already', highlighted: false),
    ]);
  });

  test('handles several matches in one snippet', () {
    final spans = ocrSnippetSpans('<mark>a</mark> and <mark>b</mark>');

    expect(spans.where((s) => s.highlighted).map((s) => s.text), ['a', 'b']);
  });

  test('an unmarked snippet is one plain span', () {
    expect(ocrSnippetSpans('plain text'), [
      (text: 'plain text', highlighted: false),
    ]);
  });

  test('an empty snippet produces no spans', () {
    expect(ocrSnippetSpans(''), isEmpty);
  });

  test('keeps stray angle brackets as literal text', () {
    final spans = ocrSnippetSpans('use <b> tags <mark>here</mark>');

    expect(spans.first, (text: 'use <b> tags ', highlighted: false));
    expect(spans.last, (text: 'here', highlighted: true));
  });

  test('an unterminated mark still yields its text', () {
    final spans = ocrSnippetSpans('start <mark>never closed');

    expect(spans, [
      (text: 'start ', highlighted: false),
      (text: 'never closed', highlighted: true),
    ]);
  });
}
