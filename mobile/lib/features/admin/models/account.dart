import 'package:manhwamaniacs/core/time/server_instant.dart';

/// One account on this instance, as `GET /auth/users` reports it.
///
/// Only an admin can ask for this, and only an admin is shown it. Registration
/// on this server is open by the owner's choice, so this is the other half of
/// that decision: the list of who took it up, and the two controls for doing
/// something about it.
class Account {
  const Account({
    required this.id,
    required this.username,
    required this.isAdmin,
    required this.isActive,
    required this.createdAt,
    required this.lastLoginAt,
    required this.sessionCount,
  });

  final int id;
  final String username;
  final bool isAdmin;
  final bool isActive;

  /// Server timestamps are naive UTC with no designator; [serverInstant]
  /// supplies the one Dart would otherwise assume was local.
  final DateTime? createdAt;

  /// Null until the account has logged in at least once.
  final DateTime? lastLoginAt;

  /// Unexpired sessions only, so deactivating an account drops this to zero.
  final int sessionCount;

  factory Account.fromJson(Map<String, dynamic> json) => Account(
        id: json['id'] as int,
        username: json['username'] as String? ?? '',
        isAdmin: json['is_admin'] as bool? ?? false,
        isActive: json['is_active'] as bool? ?? true,
        createdAt: serverInstant(json['created_at']),
        lastLoginAt: serverInstant(json['last_login_at']),
        sessionCount: (json['session_count'] as num?)?.toInt() ?? 0,
      );

  Account copyWith({bool? isActive}) => Account(
        id: id,
        username: username,
        isAdmin: isAdmin,
        isActive: isActive ?? this.isActive,
        createdAt: createdAt,
        lastLoginAt: lastLoginAt,
        sessionCount: sessionCount,
      );
}
