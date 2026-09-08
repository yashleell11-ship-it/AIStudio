import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/admin/members.dart';
import 'package:manhwamaniacs/features/admin/models/account.dart';

Account _account({
  required int id,
  String username = 'someone',
  bool isAdmin = false,
  bool isActive = true,
  DateTime? createdAt,
  DateTime? lastLoginAt,
  int sessionCount = 0,
}) =>
    Account(
      id: id,
      username: username,
      isAdmin: isAdmin,
      isActive: isActive,
      createdAt: createdAt,
      lastLoginAt: lastLoginAt,
      sessionCount: sessionCount,
    );

void main() {
  group('Account.fromJson', () {
    test('reads server timestamps as UTC, not as local time', () {
      // The server sends naive UTC with no designator. Parsed as local, a
      // "joined" date on a phone in +05:30 lands on the wrong day.
      final account = Account.fromJson(const {
        'id': 3,
        'username': 'kim',
        'is_admin': false,
        'is_active': true,
        'created_at': '2026-09-07T21:30:00',
        'last_login_at': null,
        'session_count': 2,
      });

      expect(account.createdAt!.isUtc, isTrue);
      expect(account.createdAt, DateTime.utc(2026, 9, 7, 21, 30));
      expect(account.lastLoginAt, isNull);
      expect(account.sessionCount, 2);
    });

    test('survives a row missing every optional field', () {
      final account = Account.fromJson(const {'id': 9});

      expect(account.username, '');
      expect(account.isAdmin, isFalse);
      expect(account.isActive, isTrue);
      expect(account.createdAt, isNull);
      expect(account.sessionCount, 0);
    });
  });

  group('memberRowGuard', () {
    test('refuses to manage your own account', () {
      final guard = memberRowGuard(_account(id: 1), currentUserId: 1);

      expect(guard.isSelf, isTrue);
      expect(guard.canManage, isFalse);
      expect(guard.reason, isNotNull);
    });

    test('allows every other account', () {
      final guard = memberRowGuard(_account(id: 2), currentUserId: 1);

      expect(guard.canManage, isTrue);
      expect(guard.reason, isNull);
    });

    test('manages nothing rather than everything when the viewer is unknown', () {
      // A null current user must not make every row look like someone else's.
      final guard = memberRowGuard(_account(id: 2), currentUserId: null);

      expect(guard.isSelf, isFalse);
      expect(guard.canManage, isTrue);
    });
  });

  group('sortMembers', () {
    test('puts your own row first, then oldest signup first', () {
      final rows = sortMembers(
        [
          _account(id: 4, createdAt: DateTime.utc(2026, 3)),
          _account(id: 1, createdAt: DateTime.utc(2026, 9)),
          _account(id: 7, createdAt: DateTime.utc(2026, 1, 15)),
        ],
        currentUserId: 1,
      );

      expect(rows.map((a) => a.id), [1, 7, 4]);
    });

    test('falls back to id when a row has no join date', () {
      final rows = sortMembers(
        [_account(id: 5), _account(id: 2)],
        currentUserId: null,
      );

      expect(rows.map((a) => a.id), [2, 5]);
    });

    test('does not mutate the list it was given', () {
      final original = [_account(id: 9), _account(id: 1)];
      sortMembers(original, currentUserId: null);

      expect(original.map((a) => a.id), [9, 1]);
    });
  });

  group('copy for the destructive path', () {
    test('the delete prompt names the account and says it is permanent', () {
      final prompt = deleteMemberPrompt(_account(id: 2, username: 'kim'));

      expect(prompt, contains('@kim'));
      expect(prompt, contains('cannot be undone'));
    });

    test('a failure shows the server its own words', () {
      // The self-target 400 is the case this exists for: only the server can
      // explain a refusal this client did not anticipate.
      expect(
        memberActionFailure('You cannot manage your own account.'),
        'You cannot manage your own account.',
      );
    });

    test('a failure with nothing to say still says something', () {
      expect(memberActionFailure(null), isNotEmpty);
      expect(memberActionFailure('   '), isNotEmpty);
    });
  });
}
