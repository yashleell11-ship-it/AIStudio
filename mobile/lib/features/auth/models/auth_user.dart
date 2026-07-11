/// Authenticated user as returned by the `/auth` endpoints.
///
/// Mirrors the backend `UserOut` schema 1-to-1. Immutable — a new instance is
/// created on every login / `/auth/me` refresh.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.username,
    required this.isAdmin,
    required this.createdAt,
    this.email,
    this.displayName,
    this.lastLoginAt,
  });

  final int id;
  final String username;
  final String? email;
  final String? displayName;
  final bool isAdmin;
  final DateTime createdAt;
  final DateTime? lastLoginAt;

  /// Best label for the user in the UI — the display name when set, otherwise
  /// the username.
  String get label {
    final name = displayName;
    if (name != null && name.isNotEmpty) return name;
    return username;
  }

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['id'] as int,
        username: json['username'] as String,
        email: json['email'] as String?,
        displayName: json['display_name'] as String?,
        isAdmin: json['is_admin'] as bool,
        createdAt: DateTime.parse(json['created_at'] as String),
        lastLoginAt: json['last_login_at'] != null
            ? DateTime.parse(json['last_login_at'] as String)
            : null,
      );
}
