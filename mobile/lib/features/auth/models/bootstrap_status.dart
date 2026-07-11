/// Public pre-auth probe (`GET /auth/bootstrap-status`).
///
/// Lets the client decide between a "create the first admin" flow and a normal
/// login form without exposing any user data.
class BootstrapStatus {
  const BootstrapStatus({
    required this.needsBootstrap,
    required this.registrationEnabled,
  });

  /// True while zero accounts exist: the first account created becomes the
  /// admin / owner.
  final bool needsBootstrap;

  /// Whether self-service registration is open once an admin exists.
  final bool registrationEnabled;

  factory BootstrapStatus.fromJson(Map<String, dynamic> json) =>
      BootstrapStatus(
        needsBootstrap: json['needs_bootstrap'] as bool,
        registrationEnabled: json['registration_enabled'] as bool,
      );
}
