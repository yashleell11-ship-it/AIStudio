/// Public pre-auth probe (`GET /auth/bootstrap-status`).
///
/// Lets the client decide between a "create the first admin" flow and a normal
/// login form without exposing any user data.
class BootstrapStatus {
  const BootstrapStatus({
    required this.needsBootstrap,
    required this.registrationEnabled,
    this.inviteCodeRequired = false,
    this.bootstrapOpen,
    this.registrationOpen,
    this.novelsEnabled = false,
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

  /// Whether an uninvited registration would *still* be accepted as the
  /// bootstrap admin. An empty users table only stays claimable for
  /// `MM_BOOTSTRAP_WINDOW_MINUTES`; after that the backend rejects the
  /// takeover even though `needsBootstrap` is still true. Null on a backend
  /// that predates the field — such a server never had a window, so
  /// `needsBootstrap` alone is the honest answer there.
  final bool? bootstrapOpen;

  /// Whether `POST /auth/register` could succeed at all right now (with a
  /// valid invite code where one is required). Null on a backend that
  /// predates the field; falls back to `registrationEnabled`.
  final bool? registrationOpen;

  /// Whether this deployment serves novels at all (`MM_NOVELS_ENABLED`).
  ///
  /// The production gate for every novel surface in the app: with it off the
  /// Manga/Novels switch does not render, the effective content mode is forced
  /// to manga, and nothing novel-shaped is reachable — the app must look
  /// *exactly* as it does today, not "the same but with a disabled tab".
  ///
  /// Rides on this pre-auth probe (rather than an authenticated settings
  /// call) because the client already makes it once per launch, so the novel
  /// code ships dormant and one env var on the VPS turns it on.
  ///
  /// Absent on an older backend, which is the same thing as off: a deployment
  /// that has never heard of the flag has no novel connectors to browse
  /// either.
  final bool novelsEnabled;

  /// The claim-this-server flow is only truthful while the window is open —
  /// offering it after expiry sends the user into a guaranteed rejection.
  bool get isBootstrapOpen => bootstrapOpen ?? needsBootstrap;

  /// Whether to offer a "create an account" affordance at all.
  bool get isRegistrationOpen => registrationOpen ?? registrationEnabled;

  factory BootstrapStatus.fromJson(Map<String, dynamic> json) {
    final invite = json['invite_code_required'];
    final bootstrapOpen = json['bootstrap_open'];
    final registrationOpen = json['registration_open'];
    return BootstrapStatus(
      needsBootstrap: json['needs_bootstrap'] as bool,
      registrationEnabled: json['registration_enabled'] as bool,
      // `invite is bool` (rather than an `as bool?` cast) so a key that is
      // present but the wrong type — a stale/misbehaving server — degrades to
      // "not required" instead of throwing a ParseError out of a probe the
      // login screen depends on to render at all.
      inviteCodeRequired: invite is bool ? invite : false,
      // Same tolerant read as `invite`, but degrading to null rather than
      // false: null means "server didn't say", which the getters resolve to
      // the older flags. Coercing a missing key to false would instead claim
      // the window is shut on every backend that never had one.
      bootstrapOpen: bootstrapOpen is bool ? bootstrapOpen : null,
      registrationOpen: registrationOpen is bool ? registrationOpen : null,
      // Same tolerant read as `invite`: a server that never had the flag, or
      // one answering with the wrong type, is "novels off" rather than a
      // ParseError out of the probe the login screen depends on.
      novelsEnabled: json['novels_enabled'] is bool
          ? json['novels_enabled']! as bool
          : false,
    );
  }
}
