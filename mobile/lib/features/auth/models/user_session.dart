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
        createdAt: _instant(json['created_at']),
        lastUsedAt: _instant(json['last_used_at']),
        expiresAt: _instant(json['expires_at']),
        isCurrent: json['current'] as bool? ?? false,
        userAgent: json['user_agent'] as String?,
        ipAddress: json['ip_address'] as String?,
      );
}

/// An instant reported by the backend.
///
/// Every timestamp column in this project is a naive SQLite `DATETIME` holding
/// UTC (`core/time_utils.utcnow`), so it serialises with no timezone
/// designator — and `DateTime.parse` reads an offset-less string as **local**,
/// which would shift every "last used" on the sessions screen by the device's
/// UTC offset (+5:30 turns a session in use right now into one last seen five
/// and a half hours ago). Same fix, same reason, as `bookmarkInstant` and the
/// statistics parser. A malformed timestamp degrades to the epoch rather than
/// throwing: one bad row must not cost the user the list they came to audit.
DateTime _instant(Object? raw) {
  if (raw is! String || raw.isEmpty) {
    return DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  }
  final zoned = raw.endsWith('Z') || _offsetSuffix.hasMatch(raw);
  return DateTime.tryParse(zoned ? raw : '${raw}Z')?.toUtc() ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
}

final RegExp _offsetSuffix = RegExp(r'[+-]\d{2}:?\d{2}$');
