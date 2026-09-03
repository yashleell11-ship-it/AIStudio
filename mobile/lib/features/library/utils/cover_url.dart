import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';

/// Resolves a followed series' cover URL to an absolute one. The backend
/// returns either the source's own absolute URL or a backend-relative
/// `/sources/{source}/series/{series}/cover` proxy path.
String? followedSeriesCoverUrl(String apiBaseUrl, FollowedSeries series) {
  if (series.coverUrl.isEmpty) return null;
  return resolveApiResourceUrl(apiBaseUrl, series.coverUrl);
}

/// Builds the absolute cover image URL for an online source series, matching
/// the backend route `/sources/{source_id}/series/{series_id:path}/cover`.
String sourceSeriesCoverUrl(String apiBaseUrl, String source, String seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}sources/$source/series/${Uri.encodeComponent(seriesId)}/cover';
}

/// Shared Hero tag for a library series' cover (keyed by the follow row's
/// `followed_id`), so the library grid/list and the series detail screen
/// animate as one continuous shared element rather than a hard cut. Both ends
/// must use this exact same helper.
String seriesCoverHeroTag(int followedId) => 'series-cover-$followedId';

/// Resolves a collection cover URL when the backend stores an absolute URL.
String? collectionCoverUrl(String? coverUrl) {
  if (coverUrl == null || coverUrl.isEmpty) return null;
  if (coverUrl.startsWith('http://') || coverUrl.startsWith('https://')) {
    return coverUrl;
  }
  return null;
}
