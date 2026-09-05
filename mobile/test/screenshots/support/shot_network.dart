import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Serves fixture cover bytes to `CachedNetworkImage` inside a widget test.
///
/// Covers are the one part of these screenshots that cannot come from a
/// fixture object: every cover in the app is painted by `SeriesCoverImage`,
/// which hands a URL to `CachedNetworkImage` and has no injection seam. So the
/// bytes are supplied one layer lower, at `dart:io`.
///
/// That takes three stubs, because `flutter_cache_manager` is a real cache:
///   * `HttpOverrides` — the fetch itself. `http.Client()` resolves to an
///     `IOClient` wrapping a `dart:io` `HttpClient`, which honours the global
///     override.
///   * the `path_provider` platform channel — the cache asks for a temporary
///     directory and there is no plugin registered in a test host.
///   * `sqflite` — the cache keys its metadata in SQLite; `sqflite_common_ffi`
///     (already a dev dependency) answers it without a platform channel.
///
/// This deliberately runs the *real* cache manager rather than faking it, so
/// what the screenshots capture is the same code path the shipped app uses.
/// Fixture cover bytes, keyed on request path, for the whole suite.
final Map<String, Uint8List> _shotCovers = {};

/// Puts fixture covers behind the app's real cover pipeline, for the suite.
///
/// Call once from `setUpAll`. Deliberately suite-wide rather than per-test,
/// twice over:
///
///   * `CachedNetworkImage` reaches `DefaultCacheManager`, a singleton that
///     opens its store once per isolate. A per-test cache directory gets
///     deleted out from under the next test that reuses it.
///   * That same singleton builds its `HttpFileService` — and the
///     `http.Client` inside it — exactly once, at first use. A per-test
///     `HttpOverrides` is therefore only ever consulted by the *first* test
///     that renders a cover; every later test's covers are fetched through the
///     first one's client and 404.
///
/// Both failure modes are silent: the screen still renders, just with no
/// artwork. The novel shelf shipped four blank plates that way.
///
/// Three stubs are needed because `flutter_cache_manager` is a real cache: the
/// fetch (`HttpOverrides` — `http.Client()` resolves to an `IOClient` wrapping
/// a `dart:io` `HttpClient`, which honours the global override), a temporary
/// directory (the `path_provider` channel, unimplemented in a test host), and
/// SQLite for the cache index (`sqflite_common_ffi`, already a dev
/// dependency). Running the *real* cache manager rather than faking it is the
/// point: the screenshots then come off the same code path the shipped app
/// uses.
void setUpShotCoverCache() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  final temp = Directory.systemTemp.createTempSync('mm-shot-covers-');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(
    const MethodChannel('plugins.flutter.io/path_provider'),
    (call) async => temp.path,
  );
  HttpOverrides.global = _ShotHttpOverrides();

  addTearDown(() {
    HttpOverrides.global = null;
    _shotCovers.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (temp.existsSync()) temp.deleteSync(recursive: true);
  });
}

/// Registers [covers] (request path -> PNG bytes) with the suite's server.
void addShotCovers(Map<String, Uint8List> covers) => _shotCovers.addAll(covers);

/// Lets the real cover fetches complete, then paints them.
///
/// Downloading, writing to the cache directory and decoding are all real async
/// work, which `FakeAsync` inside a test body would never advance — hence the
/// alternation between [WidgetTester.runAsync] (real time) and
/// [WidgetTester.pump] (frames).
Future<void> pumpUntilCoversLoad(WidgetTester tester, {int rounds = 40}) async {
  for (var i = 0; i < rounds; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 60)),
    );
    // Long enough to also carry `SeriesCoverImage`'s 250 ms cover fade to its
    // end, so no cover is captured mid-fade.
    await tester.pump(const Duration(milliseconds: 300));
  }
}

class _ShotHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _ShotHttpClient();
}

class _ShotHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  Duration? connectionTimeout;
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;

  @override
  Future<HttpClientRequest> getUrl(Uri url) async => _ShotRequest(url);

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async =>
      _ShotRequest(url);

  @override
  void close({bool force = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _ShotRequest implements HttpClientRequest {
  _ShotRequest(this.uri);

  @override
  final Uri uri;

  @override
  final HttpHeaders headers = _ShotHeaders();

  @override
  bool followRedirects = true;
  @override
  int maxRedirects = 5;
  @override
  int contentLength = -1;
  @override
  bool persistentConnection = true;
  @override
  bool bufferOutput = true;

  /// `IOClient` sends the body with `stream.pipe(ioRequest)`, which calls
  /// `addStream` and then `close`. A `noSuchMethod` stub returning null makes
  /// `pipe` call `.then` on null, and the fetch dies before it reaches the
  /// fixture bytes — which is exactly how these covers first came out blank.
  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();

  @override
  void add(List<int> data) {}

  @override
  Future<void> flush() async {}

  @override
  Future<HttpClientResponse> close() async {
    // ignore: avoid_print
    print('REQ ${uri.path} known=${_shotCovers.keys.length} hit=${_shotCovers.containsKey(uri.path)}');
    return _ShotResponse(_shotCovers[uri.path]);
  }

  @override
  Future<HttpClientResponse> get done => close();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _ShotHeaders implements HttpHeaders {
  final _values = <String, List<String>>{};

  @override
  List<String>? operator [](String name) => _values[name.toLowerCase()];

  @override
  String? value(String name) => _values[name.toLowerCase()]?.first;

  @override
  void add(String name, Object value, {bool preserveHeaderCase = false}) =>
      _values.putIfAbsent(name.toLowerCase(), () => []).add('$value');

  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) =>
      _values[name.toLowerCase()] = ['$value'];

  @override
  void forEach(void Function(String name, List<String> values) action) =>
      _values.forEach(action);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _ShotResponse extends Stream<List<int>> implements HttpClientResponse {
  _ShotResponse(this.bytes) {
    headers
      ..set('content-type', 'image/png')
      ..set('content-length', '${bytes?.length ?? 0}');
  }

  final Uint8List? bytes;

  @override
  int get statusCode => bytes == null ? 404 : 200;

  @override
  String get reasonPhrase => bytes == null ? 'Not Found' : 'OK';

  @override
  int get contentLength => bytes?.length ?? 0;

  @override
  final HttpHeaders headers = _ShotHeaders();

  @override
  bool get isRedirect => false;

  @override
  bool get persistentConnection => false;

  @override
  List<Cookie> get cookies => const [];

  @override
  List<RedirectInfo> get redirects => const [];

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    final body = bytes == null
        ? const Stream<List<int>>.empty()
        : Stream<List<int>>.value(bytes!);
    return body.listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
