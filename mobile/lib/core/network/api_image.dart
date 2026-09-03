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
Map<String, String>? apiImageHttpHeaders(String? bearerToken, {int? profileId}) {
  if (bearerToken == null || bearerToken.isEmpty) return null;
  return {
    'Authorization': 'Bearer $bearerToken',
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
