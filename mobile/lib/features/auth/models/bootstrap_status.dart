/// Public pre-auth probe (`GET /auth/bootstrap-status`).
///
/// Lets the client decide between a "create the first admin" flow and a normal
/// login form without exposing any user data.
class BootstrapStatus {
  const BootstrapStatus({
    required this.needsBootstrap,
    required this.registrationEnabled,
    this.inviteCodeRequired = false,
  });

  /// True while zero accounts exist: the first account created becomes the
  /// admin / owner.
  final bool needsBootstrap;

  /// Whether self-service registration is open once an admin exists.
  final bool registrationEnabled;

  /// Whether self-service registration requires an invite code. Never true
  /// during bootstrap — the first account never needs one.
  ///
  /// Parsed tolerantly: an older/not-yet-updated server that omits this key
  /// (or sends something other than a bool) is treated as "not required" so
  /// the invite field only ever appears when the server explicitly asks for
  /// it.
  final bool inviteCodeRequired;

  factory BootstrapStatus.fromJson(Map<String, dynamic> json) {
    final invite = json['invite_code_required'];
    return BootstrapStatus(
      needsBootstrap: json['needs_bootstrap'] as bool,
      registrationEnabled: json['registration_enabled'] as bool,
      // `invite is bool` (rather than an `as bool?` cast) so a key that is
      // present but the wrong type — a stale/misbehaving server — degrades to
      // "not required" instead of throwing a ParseError out of a probe the
      // login screen depends on to render at all.
      inviteCodeRequired: invite is bool ? invite : false,
    );
  }
}
