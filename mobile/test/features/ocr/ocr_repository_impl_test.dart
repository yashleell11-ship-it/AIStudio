import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/interceptors/error_interceptor.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/repositories/ocr_repository_impl.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_upload_payload.dart';
import 'package:mocktail/mocktail.dart';

/// Drives [OcrRepositoryImpl] through Dio's real request pipeline against a
/// mocked adapter, so the exact bodies and query strings `backend/routes/ocr.py`
/// receives are pinned — including the client-side trimming, which is the one
/// thing standing between a 60-page OCR run and a 422 that discards it.
class _MockHttpClientAdapter extends Mock implements HttpClientAdapter {}

class _FakeRequestOptions extends Fake implements RequestOptions {}

ResponseBody _jsonBody(Map<String, dynamic> body, int statusCode) {
  return ResponseBody.fromString(
    jsonEncode(body),
    statusCode,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );
}

const _id = (sourceId: 'asura', seriesKey: 'solo/leveling', chapterKey: 'ch/1');

void main() {
  setUpAll(() => registerFallbackValue(_FakeRequestOptions()));

  late _MockHttpClientAdapter adapter;
  late OcrRepositoryImpl repository;

  setUp(() {
    adapter = _MockHttpClientAdapter();
    final dio = Dio(BaseOptions(baseUrl: 'https://mm.test'))
      ..httpClientAdapter = adapter
      ..interceptors.add(ErrorInterceptor());
    repository = OcrRepositoryImpl(dio);
  });

  group('POST /ocr/chapter', () {
    test('sends the source-native triple and the recognized pages', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'word_count': 812}, 200);
      });

      final result = await repository.uploadChapter(
        id: _id,
        engine: 'vision',
        chapterNumber: 12.5,
        pages: const [
          PageText(page: 1, text: 'hello'),
          PageText(
            page: 2,
            text: 'world',
            boxes: [OcrTextBox(text: 'world', x: 0.1, confidence: 0.9)],
          ),
        ],
      );

      expect(result.isOk, isTrue);
      expect(result.value, 812);

      expect(captured!.path, '/ocr/chapter');
      final body = captured!.data! as Map<String, dynamic>;
      expect(body['source_id'], 'asura');
      // Keys travel opaque — never split, never re-encoded, slashes and all.
      expect(body['series_key'], 'solo/leveling');
      expect(body['chapter_key'], 'ch/1');
      expect(body['chapter_number'], 12.5);
      expect(body['engine'], 'vision');
      expect(body['pages'], [
        {'page': 1, 'text': 'hello'},
        {
          'page': 2,
          'text': 'world',
          'boxes': [
            {'text': 'world', 'x': 0.1, 'confidence': 0.9},
          ],
        },
      ]);
    });

    test('omits chapter_number and language when the caller has neither',
        () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'word_count': 1}, 200);
      });

      await repository.uploadChapter(
        id: _id,
        engine: 'mlkit',
        pages: const [PageText(page: 1, text: 'hi')],
      );

      final body = captured!.data! as Map<String, dynamic>;
      expect(body.containsKey('chapter_number'), isFalse);
      expect(body.containsKey('language'), isFalse);
    });

    test('trims an over-limit payload rather than letting the server 422 it',
        () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'word_count': 1}, 200);
      });

      await repository.uploadChapter(
        id: _id,
        engine: 'vision',
        pages: [
          for (var i = 1; i <= 3; i++)
            PageText(page: i, text: 'a' * (kOcrMaxPageTextChars + 100)),
        ],
      );

      final pages =
          (captured!.data! as Map<String, dynamic>)['pages']! as List<dynamic>;
      for (final page in pages) {
        expect(
          ((page as Map<String, dynamic>)['text']! as String).length,
          kOcrMaxPageTextChars,
        );
      }
    });

    test('refuses an empty page list without spending a request', () async {
      final result = await repository.uploadChapter(
        id: _id,
        engine: 'vision',
        pages: const [],
      );

      expect(result.isErr, isTrue);
      verifyNever(() => adapter.fetch(any(), any(), any()));
    });

    test('surfaces the server\'s error rather than swallowing it', () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody(
          {'code': 'ocr_payload_too_large', 'message': 'OCR payload too large.'},
          422,
        ),
      );

      final result = await repository.uploadChapter(
        id: _id,
        engine: 'vision',
        pages: const [PageText(page: 1, text: 'hi')],
      );

      expect(result.isErr, isTrue);
      expect(result.error, isA<ApiError>());
    });
  });

  group('GET /ocr/coverage', () {
    test('maps chapter word counts and answers "is this one covered"',
        () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody({
          'source_id': 'asura',
          'series_key': 'solo/leveling',
          'chapters': [
            {'chapter_key': 'ch/1', 'word_count': 812},
            {'chapter_key': 'ch/2', 'word_count': 0},
          ],
        }, 200,),
      );

      final result = await repository.coverage(
        sourceId: 'asura',
        seriesKey: 'solo/leveling',
      );

      expect(result.isOk, isTrue);
      expect(result.value.covers('ch/1'), isTrue);
      // A 0-word row is a failed contribution, not a finished chapter.
      expect(result.value.covers('ch/2'), isFalse);
      expect(result.value.covers('ch/3'), isFalse);
      expect(result.value.coveredChapterCount, 1);
    });
  });

  group('GET /ocr/search', () {
    test('parses items, and derives has_more when the server omits it',
        () async {
      when(() => adapter.fetch(any(), any(), any())).thenAnswer(
        (_) async => _jsonBody({
          'items': [
            {
              'source_id': 'asura',
              'series_key': 'solo/leveling',
              'chapter_key': 'ch/1',
              'word_count': 812,
              'engine': 'vision',
              'snippet': 'I told <mark>you</mark> already',
              'highlighted_terms': ['you'],
            },
          ],
          'total': 30,
          'offset': 0,
          'limit': 20,
        }, 200,),
      );

      final result = await repository.search('you');

      expect(result.isOk, isTrue);
      final page = result.value;
      expect(page.items.single.identity, _id);
      expect(page.items.single.highlightedTerms, ['you']);
      expect(page.total, 30);
      expect(page.hasMore, isTrue);
    });

    test('sends the query with its paging parameters', () async {
      RequestOptions? captured;
      when(() => adapter.fetch(any(), any(), any())).thenAnswer((inv) async {
        captured = inv.positionalArguments[0] as RequestOptions;
        return _jsonBody({'items': <dynamic>[], 'total': 0, 'offset': 0, 'limit': 20}, 200);
      });

      await repository.search('dragon', limit: 5, offset: 10);

      expect(captured!.path, '/ocr/search');
      expect(captured!.queryParameters, {
        'q': 'dragon',
        'limit': 5,
        'offset': 10,
      });
    });
  });
}
