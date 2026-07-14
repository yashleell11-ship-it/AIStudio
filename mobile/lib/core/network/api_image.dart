/// Helpers for loading images from authenticated ManhwaManiacs API routes.
///
/// JSON API calls go through Dio with the bearer token, but [CachedNetworkImage]
/// and [Image.network] load URLs directly and must attach the same credential.
library;

/// HTTP headers for proxied library/source cover and reader page images.
Map<String, String>? apiImageHttpHeaders(String? bearerToken) {
  if (bearerToken == null || bearerToken.isEmpty) return null;
  return {'Authorization': 'Bearer $bearerToken'};
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
