import 'package:manhwamaniacs/features/auth/models/auth_user.dart';

/// Response envelope for `/auth/login` and `/auth/register`: the authenticated
/// [user] plus the bearer [token] sent as `Authorization: Bearer <token>` on
/// every subsequent request.
class AuthResponse {
  const AuthResponse({required this.user, required this.token});

  final AuthUser user;
  final String token;

  factory AuthResponse.fromJson(Map<String, dynamic> json) => AuthResponse(
        user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
        token: json['token'] as String,
      );
}
