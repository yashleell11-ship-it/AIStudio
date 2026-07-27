import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/auth/models/auth_response.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/bootstrap_status.dart';

void main() {
  final fullJson = <String, dynamic>{
    'id': 7,
    'username': 'reader',
    'email': 'reader@example.com',
    'display_name': 'Avid Reader',
    'is_admin': true,
    'created_at': '2024-01-01T00:00:00',
    'last_login_at': '2024-06-01T12:00:00',
  };

  group('AuthUser.fromJson', () {
    test('parses all fields', () {
      final user = AuthUser.fromJson(fullJson);
      expect(user.id, 7);
      expect(user.username, 'reader');
      expect(user.email, 'reader@example.com');
      expect(user.displayName, 'Avid Reader');
      expect(user.isAdmin, isTrue);
      expect(user.createdAt, DateTime.parse('2024-01-01T00:00:00'));
      expect(user.lastLoginAt, DateTime.parse('2024-06-01T12:00:00'));
    });

    test('handles null optional fields', () {
      final json = Map<String, dynamic>.from(fullJson)
        ..['email'] = null
        ..['display_name'] = null
        ..['last_login_at'] = null;
      final user = AuthUser.fromJson(json);
      expect(user.email, isNull);
      expect(user.displayName, isNull);
      expect(user.lastLoginAt, isNull);
    });

    test('label falls back to username when display name is absent', () {
      final json = Map<String, dynamic>.from(fullJson)..['display_name'] = null;
      expect(AuthUser.fromJson(json).label, 'reader');
    });

    test('label prefers display name when present', () {
      expect(AuthUser.fromJson(fullJson).label, 'Avid Reader');
    });
  });

  group('AuthUser.toJson', () {
    test('round-trips every field through fromJson', () {
      // The offline cold start restores a session from this blob, so a field
      // lost here is a field the app cannot see with the server down.
      final restored = AuthUser.fromJson(AuthUser.fromJson(fullJson).toJson());
      expect(restored.id, 7);
      expect(restored.username, 'reader');
      expect(restored.email, 'reader@example.com');
      expect(restored.displayName, 'Avid Reader');
      expect(restored.isAdmin, isTrue);
      expect(restored.createdAt, DateTime.parse('2024-01-01T00:00:00'));
      expect(restored.lastLoginAt, DateTime.parse('2024-06-01T12:00:00'));
    });

    test('round-trips null optionals', () {
      final json = Map<String, dynamic>.from(fullJson)
        ..['email'] = null
        ..['display_name'] = null
        ..['last_login_at'] = null;
      final restored = AuthUser.fromJson(AuthUser.fromJson(json).toJson());
      expect(restored.email, isNull);
      expect(restored.displayName, isNull);
      expect(restored.lastLoginAt, isNull);
    });
  });

  group('AuthResponse.fromJson', () {
    test('parses the nested user and token', () {
      final response = AuthResponse.fromJson({
        'user': fullJson,
        'token': 'secret-token',
      });
      expect(response.token, 'secret-token');
      expect(response.user.username, 'reader');
    });
  });

  group('BootstrapStatus.fromJson', () {
    test('parses flags', () {
      final status = BootstrapStatus.fromJson({
        'needs_bootstrap': true,
        'registration_enabled': false,
      });
      expect(status.needsBootstrap, isTrue);
      expect(status.registrationEnabled, isFalse);
    });
  });
}
