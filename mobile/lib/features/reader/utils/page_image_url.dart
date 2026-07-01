String readerPageImageUrl(String apiBaseUrl, int pageId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl.substring(0, apiBaseUrl.length - 1) : apiBaseUrl;
  return '$base/reader/page/$pageId/image';
}
