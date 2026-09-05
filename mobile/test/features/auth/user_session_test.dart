import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';

Map<String, dynamic> _json({
  String lastUsed = '2026-09-05T10:00:00',
  bool current = false,
  Object? userAgent = 'Dart/3.5 (dart:io)',
  Object? ip = '10.0.0.4',
}) =>
    {
      'id': 7,
      'created_at': '2026-09-01T08:30:00',
      'last_used_at': lastUsed,
      'expires_at': '2026-10-01T08:30:00',
      'user_agent': userAgent,
      'ip_address': ip,
      'current': current,
    };

void main() {
  group('UserSession.fromJson', () {
    test('reads the flat SessionOut shape', () {
      final session = UserSession.fromJson(_json(current: true));

      expect(session.id, 7);
      expect(session.isCurrent, isTrue);
      expect(session.userAgent, 'Dart/3.5 (dart:io)');
      expect(session.ipAddress, '10.0.0.4');
    });

    // The backend stores naive UTC and serialises it without a designator, so
    // `DateTime.parse` alone would read it as local — turning a session in use
    // right now into one last seen five and a half hours ago on an IST phone.
    test('an offset-less timestamp is UTC, not local', () {
      final session = UserSession.fromJson(_json());

      expect(session.lastUsedAt.isUtc, isTrue);
      expect(session.lastUsedAt, DateTime.utc(2026, 9, 5, 10));
    });

    test('a timestamp that already carries a zone is not shifted again', () {
      final session = UserSession.fromJson(
        _json(lastUsed: '2026-09-05T10:00:00Z'),
      );

      expect(session.lastUsedAt, DateTime.utc(2026, 9, 5, 10));
    });

    test('a session with no agent or IP still parses', () {
      final session = UserSession.fromJson(_json(userAgent: null, ip: null));

      expect(session.userAgent, isNull);
      expect(session.ipAddress, isNull);
    });

    // One malformed row must not cost the user the list they opened the screen
    // to audit.
    test('a malformed timestamp degrades instead of throwing', () {
      final session = UserSession.fromJson(_json(lastUsed: 'not-a-date'));

      expect(session.lastUsedAt.millisecondsSinceEpoch, 0);
    });

    test('a server that omits `current` is treated as not-this-device', () {
      final json = _json()..remove('current');

      expect(UserSession.fromJson(json).isCurrent, isFalse);
    });
  });
}
