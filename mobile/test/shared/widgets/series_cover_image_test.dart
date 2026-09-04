import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/core/network/interceptors/auth_interceptor.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

import '../../support/test_overrides.dart';

const _proxyCover =
    'http://127.0.0.1:8000/sources/asurascans/series/orv/cover';

/// Mounts one cover and hands back the [CachedNetworkImage] it built — the
/// widget that actually owns the request URL and the headers.
Future<CachedNetworkImage> _pumpCover(
  WidgetTester tester, {
  String url = _proxyCover,
  double? width,
  double? displayWidth,
  required double devicePixelRatio,
}) async {
  tester.view.devicePixelRatio = devicePixelRatio;
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authTokenStoreProvider
            .overrideWithValue(AuthTokenStore()..token = 'secret-token'),
        activeProfileOverride(),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 200,
              height: 300,
              child: SeriesCoverImage(
                url: url,
                width: width,
                displayWidth: displayWidth,
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();

  return tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage));
}

void main() {
  group('SeriesCoverImage cover sizing', () {
    testWidgets('asks the proxy for the slot width in device pixels',
        (tester) async {
      final image = await _pumpCover(tester, width: 120, devicePixelRatio: 3);

      // 120 logical px at 3x is 360 device px. The backend snaps that onto its
      // own ladder; nothing here mirrors the ladder.
      expect(image.imageUrl, '$_proxyCover?w=360');
    });

    testWidgets('takes displayWidth for a cover that fills its parent',
        (tester) async {
      final image =
          await _pumpCover(tester, displayWidth: 100, devicePixelRatio: 2);

      expect(image.imageUrl, '$_proxyCover?w=200');
    });

    testWidgets('displayWidth wins over the painted box width', (tester) async {
      final image = await _pumpCover(
        tester,
        width: 44,
        displayWidth: 120,
        devicePixelRatio: 1,
      );

      expect(image.imageUrl, '$_proxyCover?w=120');
    });

    testWidgets('clamps a full-bleed slot on a 3x screen', (tester) async {
      final image =
          await _pumpCover(tester, displayWidth: 400, devicePixelRatio: 3);

      expect(image.imageUrl, '$_proxyCover?w=$kMaxCoverRequestWidth');
    });

    testWidgets('asks for the original when no slot width is stated',
        (tester) async {
      final image = await _pumpCover(tester, devicePixelRatio: 3);

      expect(image.imageUrl, _proxyCover);
    });

    testWidgets('leaves a source\'s own absolute cover URL alone',
        (tester) async {
      const cdn = 'https://uploads.example.org/covers/abc.jpg';
      final image =
          await _pumpCover(tester, url: cdn, width: 120, devicePixelRatio: 3);

      expect(image.imageUrl, cdn);
    });

    testWidgets('sends Accept so the proxy may answer with WebP',
        (tester) async {
      final image = await _pumpCover(tester, width: 120, devicePixelRatio: 3);

      expect(image.httpHeaders, isNotNull);
      expect(image.httpHeaders!['Accept'], contains('image/webp'));
      expect(image.httpHeaders!['Authorization'], 'Bearer secret-token');
    });

    testWidgets('one slot width is one cache key, whatever the widget rebuilds',
        (tester) async {
      // CachedNetworkImage keys its disk cache on the URL, so a width that
      // wobbled between rebuilds would re-download the same cover.
      final first = await _pumpCover(tester, width: 120, devicePixelRatio: 3);
      await tester.pump();
      final second =
          tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage));

      expect(second.imageUrl, first.imageUrl);
    });
  });
}
