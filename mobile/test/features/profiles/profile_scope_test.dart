import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';

void main() {
  group('isProfileScopeError', () {
    test('true for the backend per-profile guard rejections', () {
      expect(
        isProfileScopeError(
          const ApiError(
            statusCode: 400,
            code: 'profile_required',
            message: 'Active profile required',
          ),
        ),
        isTrue,
      );
      expect(
        isProfileScopeError(
          const ApiError(
            statusCode: 404,
            code: 'profile_not_found',
            message: 'Unknown profile',
          ),
        ),
        isTrue,
      );
    });

    test('false for other API errors and non-API errors', () {
      expect(
        isProfileScopeError(
          const ApiError(statusCode: 400, code: 'bad_request', message: 'x'),
        ),
        isFalse,
      );
      expect(isProfileScopeError(const TimeoutError()), isFalse);
      expect(
        isProfileScopeError(const NetworkError(message: 'down')),
        isFalse,
      );
    });
  });

  test('the profile-scoped invalidator set is non-empty', () {
    // Guards against an accidental empty list silently disabling switch-time
    // cache invalidation.
    expect(profileScopedInvalidators, isNotEmpty);
  });
}
