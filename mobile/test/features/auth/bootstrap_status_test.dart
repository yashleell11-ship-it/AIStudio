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

  group('bootstrap window policy', () {
    // The backend keeps an empty users table claimable for only
    // MM_BOOTSTRAP_WINDOW_MINUTES. `needs_bootstrap` stays true after that —
    // it only reports "zero accounts" — so `bootstrap_open` is the field that
    // actually says whether a takeover would be accepted.
    test('an expired window closes the claim flow even with zero accounts', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': true,
        'registration_enabled': false,
        'bootstrap_open': false,
      });

      expect(status.needsBootstrap, isTrue);
      expect(status.isBootstrapOpen, isFalse);
    });

    test('an open window keeps the claim flow available', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': true,
        'registration_enabled': false,
        'bootstrap_open': true,
      });

      expect(status.isBootstrapOpen, isTrue);
    });

    test('registration_open overrides registration_enabled', () {
      // The two differ whenever registration is enabled but unsatisfiable —
      // e.g. enabled with an invite code the server has not been given.
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': false,
        'registration_enabled': true,
        'registration_open': false,
      });

      expect(status.registrationEnabled, isTrue);
      expect(status.isRegistrationOpen, isFalse);
    });

    test('a backend without the fields falls back to the older flags', () {
      // A server that predates the window never had one, so "zero accounts"
      // really does mean claimable there. Coercing the absent key to false
      // would lock the owner out of a first-run server.
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': true,
        'registration_enabled': true,
      });

      expect(status.bootstrapOpen, isNull);
      expect(status.registrationOpen, isNull);
      expect(status.isBootstrapOpen, isTrue);
      expect(status.isRegistrationOpen, isTrue);
    });

    test('non-bool window fields degrade to the fallback, not to false', () {
      final status = BootstrapStatus.fromJson(const {
        'needs_bootstrap': true,
        'registration_enabled': true,
        'bootstrap_open': 'maybe',
        'registration_open': 1,
      });

      expect(status.isBootstrapOpen, isTrue);
      expect(status.isRegistrationOpen, isTrue);
    });
  });
}
