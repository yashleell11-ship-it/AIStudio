/// Helpers for loading images from authenticated ManhwaManiacs API routes.
///
/// JSON API calls go through Dio with the bearer token, but [CachedNetworkImage]
/// and [Image.network] load URLs directly and must attach the same credential.
library;

/// HTTP headers for proxied library/source cover and reader page images.
///
/// [profileId] is the active reading profile (`X-Profile-Id`). The image proxy
/// resolves the 18+ gate from that header exactly like the JSON routes do —
/// without it a mature-enabled profile's request falls back to the instance
/// default gate and the proxy 404s covers/pages the same profile's JSON calls
/// can see. Passed as a plain value so this file stays profile-agnostic.
///
/// `Accept` is not politeness, it is ~20% of the cover payload. The cover
/// proxy only serves WebP to a client that names `image/webp` literally — a
/// bare `*/*` is deliberately read as "no WebP", because a client that cannot
/// decode it shows a broken cover while one that can only pays some bytes.
/// Neither `dart:io`'s HTTP client nor `CachedNetworkImage` sends an `Accept`
/// of its own, so without this every cover comes back JPEG.
Map<String, String>? apiImageHttpHeaders(String? bearerToken, {int? profileId}) {
  if (bearerToken == null || bearerToken.isEmpty) return null;
  return {
    'Authorization': 'Bearer $bearerToken',
    'Accept': 'image/webp,image/jpeg,*/*',
    if (profileId != null) 'X-Profile-Id': '$profileId',
  };
}

/// Resolve a relative API path (e.g. `/sources/.../cover`) to an absolute URL.
String resolveApiResourceUrl(String apiBaseUrl, String pathOrUrl) {
  if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
    return pathOrUrl;
  }
  final base = apiBaseUrl.endsWith('/')
      ? apiBaseUrl.substring(0, apiBaseUrl.length - 1)
      : apiBaseUrl;
  final path = pathOrUrl.startsWith('/') ? pathOrUrl : '/$pathOrUrl';
  return '$base$path';
}

/// Ceiling, in device pixels, on the `?w=` a cover request may ask for.
///
/// The widest cover slot in the app is the series-detail hero, which spans the
/// content column: ~1150 device px on a 3x phone, and unbounded on a tablet in
/// landscape without a cap. Past this a cover is asking for more detail than
/// any screen here can show.
///
/// This is a ceiling, not a size. The backend owns the width ladder and snaps
/// whatever arrives onto it, so the ladder is deliberately not repeated on
/// this side — a client that mirrored it would have to be redeployed to
/// benefit from a new rung.
const int kMaxCoverRequestWidth = 1080;

/// The `?w=` a cover slot [logicalWidth] logical pixels wide should ask for at
/// [devicePixelRatio], or null for "ask for the original".
///
/// Null rather than an exception for a width that is unbounded, zero or NaN:
/// an over-sized cover is a performance problem, a crash on a layout edge case
/// is a bug. This mirrors the backend's own posture, where every resize
/// failure degrades to serving the original.
int? coverRequestWidth(double? logicalWidth, double devicePixelRatio) {
  if (logicalWidth == null || !logicalWidth.isFinite || logicalWidth <= 0) {
    return null;
  }
  if (!devicePixelRatio.isFinite || devicePixelRatio <= 0) return null;
  final devicePixels = (logicalWidth * devicePixelRatio).round();
  if (devicePixels <= 0) return null;
  return devicePixels > kMaxCoverRequestWidth
      ? kMaxCoverRequestWidth
      : devicePixels;
}

/// Appends `?w=[width]` to a backend cover-proxy URL; anything else comes back
/// untouched.
///
/// The test is the route's own shape, because the same field carries two very
/// different things: the backend's `/sources/{source}/series/{series}/cover`
/// proxy, which understands `?w=`, and a source's own absolute CDN link, which
/// the backend hands through verbatim. Bolting an unknown query parameter onto
/// somebody else's (possibly signed) URL is how covers stop loading, so a URL
/// that is not literally the proxy route is left exactly as published. It also
/// makes this idempotent: a URL that already carries `?w=` no longer ends in
/// `/cover`.
String coverUrlAtWidth(String url, int? width) {
  if (width == null || !url.endsWith('/cover')) return url;
  return '$url?w=$width';
}
