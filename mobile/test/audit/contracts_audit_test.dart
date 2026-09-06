// Audit shard "contracts": server timestamps are naive UTC (no `Z`), but
// several mobile models parse them with a bare `DateTime.parse`/`tryParse`,
// which Dart reads as LOCAL wall-clock time. The screens then call
// `.toLocal()` on the result (a no-op on a local DateTime), so the UTC
// wall-clock is shown as if it were local — off by the device's UTC offset.
//
// The wire strings below are byte-for-byte what the backend emits
// (`progress_service._iso`, `update_service.serialize_notification`,
// `profile_service.serialize`, `followed_series_service.serialize`,
// `UserOut` via FastAPI's datetime encoder): `datetime.isoformat()` on a
// naive datetime. `2026-09-05 05:37:04.708165` is the newest live
// `chapter_progress.last_read_at` on the VPS (read-only query, 2026-09-06).
//
// Run with a non-UTC zone to see the concrete shift:
//   TZ=Asia/Kolkata flutter test test/audit/contracts_audit_test.dart
//
// The `isUtc` assertions fail in EVERY zone; the instant assertions fail in
// every zone except UTC.
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/auth/models/auth_user.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/models/update_settings.dart';

const wire = '2026-09-05T05:37:04.708165';
final expected = DateTime.utc(2026, 9, 5, 5, 37, 4, 708, 165);

void main() {
  group('naive-UTC server timestamps are read as local time', () {
    test('ReadingHistoryItem.last_read_at (reading_history_screen shows it)',
        () {
      final item = ReadingHistoryItem.fromJson({
        'id': 1,
        'source_id': 's',
        'series_key': 'k',
        'chapter_key': 'c',
        'chapter_number': 1.0,
        'last_page': 1,
        'page_count': 10,
        'is_completed': false,
        'last_read_at': wire,
      });
      expect(
        item.lastReadAt!.isUtc,
        isTrue,
        reason: 'server sent UTC; the screen calls .toLocal() on this',
      );
      expect(item.lastReadAt!.toUtc(), expected);
    });

    test('UpdateNotification.created_at (updates_screen shows it)', () {
      final n = UpdateNotification.fromJson({
        'id': 1,
        'followed_series_id': 1,
        'source_id': 's',
        'series_key': 'k',
        'chapter_key': 'c',
        'chapter_title': 't',
        'chapter_number': 1.0,
        'is_read': false,
        'created_at': wire,
      });
      expect(n.createdAt!.isUtc, isTrue);
      expect(n.createdAt!.toUtc(), expected);
    });

    test('ReadingProgress.last_read_at', () {
      final p = ReadingProgress.fromJson({
        'id': 1,
        'source_id': 's',
        'series_key': 'k',
        'chapter_key': 'c',
        'chapter_number': 1.0,
        'last_page': 1,
        'page_count': 10,
        'scroll_offset_px': 0,
        'is_completed': false,
        'started_at': wire,
        'last_read_at': wire,
        'completed_at': null,
        'time_spent_seconds': 0,
      });
      expect(p.lastReadAt!.isUtc, isTrue);
      expect(p.lastReadAt!.toUtc(), expected);
    });

    test('ContinueReadingItem.last_read_at', () {
      final c = ContinueReadingItem.fromJson({
        'source_id': 's',
        'series_key': 'k',
        'chapter_key': 'c',
        'chapter_number': 1.0,
        'last_page': 1,
        'page_count': 10,
        'last_read_at': wire,
      });
      expect(c.lastReadAt!.isUtc, isTrue);
      expect(c.lastReadAt!.toUtc(), expected);
    });

    test('FollowedSeries.last_checked_at / created_at / updated_at', () {
      final f = FollowedSeries.fromJson({
        'id': 1,
        'source_id': 's',
        'series_key': 'k',
        'title': 't',
        'cover_url': '/x',
        'is_favorite': false,
        'reading_status': 'reading',
        'notify': true,
        'sort_order': 0,
        'content_rating': null,
        'rating': 'safe',
        'mature_override': null,
        'chapter_count': 0,
        'last_checked_at': wire,
        'created_at': wire,
        'updated_at': wire,
      });
      expect(f.lastCheckedAt!.isUtc, isTrue);
      expect(f.lastCheckedAt!.toUtc(), expected);
    });

    test('AuthUser.created_at / last_login_at', () {
      final u = AuthUser.fromJson({
        'id': 1,
        'username': 'u',
        'email': null,
        'display_name': null,
        'is_admin': true,
        'created_at': wire,
        'last_login_at': wire,
      });
      expect(u.lastLoginAt!.isUtc, isTrue);
      expect(u.lastLoginAt!.toUtc(), expected);
    });

    test('Profile.created_at', () {
      final p = Profile.fromJson({
        'id': 1,
        'name': 'p',
        'avatar_key': 'default',
        'mood': 'default',
        'sort_order': 0,
        'mature_content_enabled': false,
        'created_at': wire,
      });
      expect(p.createdAt.isUtc, isTrue);
      expect(p.createdAt.toUtc(), expected);
    });

    test('UpdateSettings.last_run_at', () {
      final s = UpdateSettings.fromJson({
        'enabled': true,
        'check_interval_minutes': 60,
        'notify_enabled': true,
        'check_on_startup': false,
        'last_run_at': wire,
      });
      expect(s.lastRunAt!.isUtc, isTrue);
      expect(s.lastRunAt!.toUtc(), expected);
    });
  });

  group('control: the models that already carry the fix', () {
    test('UserSession appends Z and normalises to UTC', () {
      final s = UserSession.fromJson({
        'id': 1,
        'created_at': wire,
        'last_used_at': wire,
        'expires_at': wire,
        'user_agent': null,
        'ip_address': null,
        'current': true,
      });
      expect(s.lastUsedAt.isUtc, isTrue);
      expect(s.lastUsedAt, expected);
    });
  });
}
