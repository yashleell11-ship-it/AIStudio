import 'package:manhwamaniacs/core/time/server_instant.dart';

/// One live server-side session for the signed-in account, as returned by
/// `GET /auth/sessions`.
///
/// Mirrors the backend `SessionOut` schema 1-to-1. [isCurrent] is the server's
/// own answer (it compares the presented token's hash), never something the
/// client infers — the raw token is never available here to compare against.
class UserSession {
  const UserSession({
    required this.id,
    required this.createdAt,
    required this.lastUsedAt,
    required this.expiresAt,
    required this.isCurrent,
    this.userAgent,
    this.ipAddress,
  });

  final int id;
  final DateTime createdAt;
  final DateTime lastUsedAt;
  final DateTime expiresAt;

  /// True for the session this device is signed in with. Exactly one row in a
  /// `GET /auth/sessions` response carries it.
  final bool isCurrent;

  final String? userAgent;
  final String? ipAddress;

  factory UserSession.fromJson(Map<String, dynamic> json) => UserSession(
        id: json['id'] as int,
        createdAt: serverInstant(json['created_at']) ?? _epoch,
        lastUsedAt: serverInstant(json['last_used_at']) ?? _epoch,
        expiresAt: serverInstant(json['expires_at']) ?? _epoch,
        isCurrent: json['current'] as bool? ?? false,
        userAgent: json['user_agent'] as String?,
        ipAddress: json['ip_address'] as String?,
      );
}

/// The floor for a session timestamp the server did not send, or sent
/// unparseably: one bad row must not cost the user the list of live
/// sessions they came to audit. Every readable one is normalised by
/// [serverInstant] — see there for why the designator has to be supplied.
final DateTime _epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
