import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';

/// Federated search across the local library and every enabled remote source.
///
/// Backed by `GET /sources/search`. The shared Dio already attaches the
/// `X-Profile-Id` header and bearer token, so results are profile- and
/// mature-scoped server-side.
abstract interface class GlobalSearchRepository {
  Future<Result<GlobalSearchResult>> search(
    String query, {
    int page = 1,
    int perPage = 40,
  });
}
