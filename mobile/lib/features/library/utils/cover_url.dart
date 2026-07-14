import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';

/// Builds the absolute cover image URL for a library series.
String seriesCoverUrl(String apiBaseUrl, int seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}library/covers/$seriesId';
}

/// Builds the absolute cover image URL for an online source series, matching
/// the backend route `/sources/{source_id}/series/{series_id:path}/cover`.
String sourceSeriesCoverUrl(String apiBaseUrl, String source, String seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}sources/$source/series/${Uri.encodeComponent(seriesId)}/cover';
}

/// Resolves the best cover URL for a followed/tracked series. Prefers the local
/// library cover when the series has been imported (`localSeriesId`), otherwise
/// falls back to the online source cover. Returns null only when neither a
/// local id nor a usable source+seriesId is available.
String? trackerCoverUrl(String apiBaseUrl, SeriesTracker t) {
  final localId = t.localSeriesId;
  if (localId != null) return seriesCoverUrl(apiBaseUrl, localId);
  if (t.source.isNotEmpty && t.seriesId.isNotEmpty) {
    return sourceSeriesCoverUrl(apiBaseUrl, t.source, t.seriesId);
  }
  return null;
}

/// Shared Hero tag for a library series' cover, so the library grid/list and
/// the series detail screen animate as one continuous shared element rather
/// than a hard cut. Both ends must use this exact same helper.
String seriesCoverHeroTag(int seriesId) => 'series-cover-$seriesId';

/// Resolves a collection cover URL when the backend stores an absolute URL.
String? collectionCoverUrl(String? coverPath) {
  if (coverPath == null || coverPath.isEmpty) return null;
  if (coverPath.startsWith('http://') || coverPath.startsWith('https://')) {
    return coverPath;
  }
  return null;
}
