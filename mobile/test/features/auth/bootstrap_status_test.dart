import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';

void main() {
  group('BootstrapStatus.fromJson', () {
    test('parses invite_code_required when present', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': false,
        'registration_enabled': true,
        'invite_code_required': true,
      });

      expect(status.inviteCodeRequired, isTrue);
    });

    test('an absent invite_code_required defaults to not required', () {
      // The contract this client was built against before the backend's
      // invite-code work landed — an older server that has never heard of the
      // flag must not accidentally gate registration client-side.
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': false,
        'registration_enabled': true,
      });

      expect(status.inviteCodeRequired, isFalse);
    });

    test('a non-bool invite_code_required is tolerated as not required', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': false,
        'registration_enabled': true,
        'invite_code_required': 'yes',
      });

      expect(status.inviteCodeRequired, isFalse);
    });

    test('needs_bootstrap and registration_enabled still parse', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': true,
        'registration_enabled': false,
      });

      expect(status.needsBootstrap, isTrue);
      expect(status.registrationEnabled, isFalse);
    });
  });
}
