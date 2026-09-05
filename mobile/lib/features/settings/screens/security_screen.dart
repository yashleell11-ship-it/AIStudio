import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/providers/sessions_provider.dart';
import 'package:manhwamaniacs/features/auth/utils/session_device_label.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/features/library/utils/reading_time_format.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Account security: change the password, see every device signed in, and cut
/// them all off.
///
/// Pushed imperatively from the Settings account card rather than given a
/// route of its own — the same call the theme gallery makes, and for the same
/// reason: it is a page you reach from one place inside Settings, not a
/// destination anything deep-links to.
class SecurityScreen extends StatelessWidget {
  const SecurityScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Password & security')),
      body: ListView(
        padding: EdgeInsets.all(context.space.xl2),
        children: [
          const _ChangePasswordCard(),
          SizedBox(height: context.space.xl2),
          const _SessionsCard(),
          SizedBox(height: context.space.xl2),
          const _SignOutEverywhereCard(),
        ],
      ),
    );
  }
}

// ── Change password ──────────────────────────────────────────────────────

class _ChangePasswordCard extends ConsumerStatefulWidget {
  const _ChangePasswordCard();

  @override
  ConsumerState<_ChangePasswordCard> createState() =>
      _ChangePasswordCardState();
}

class _ChangePasswordCardState extends ConsumerState<_ChangePasswordCard> {
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();

  var _pending = false;
  String? _errorMessage;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  /// Client-side checks only for what the server cannot answer for us (the two
  /// new-password boxes agreeing) and the one rule it publishes verbatim
  /// (`core/auth.MIN_PASSWORD_LENGTH`), worded exactly as the server words it
  /// so a rejection reads the same whichever side caught it. Everything else —
  /// whether the current password is right above all — is the server's call,
  /// and its answer is shown unedited.
  String? _validate(String current, String next, String confirm) {
    if (current.isEmpty || next.isEmpty) {
      return 'Enter your current and new password.';
    }
    if (next.length < 8) return 'Password must be at least 8 characters.';
    if (next != confirm) return "Passwords don't match.";
    return null;
  }

  Future<void> _submit() async {
    if (_pending) return;
    // The three plaintexts live in locals for exactly one request and are wiped
    // from the fields the moment it succeeds. Nothing here logs them, and the
    // repository puts them in the POST body, never a URL.
    final current = _currentController.text;
    final next = _newController.text;
    final confirm = _confirmController.text;

    final validationError = _validate(current, next, confirm);
    if (validationError != null) {
      setState(() => _errorMessage = validationError);
      return;
    }

    setState(() {
      _pending = true;
      _errorMessage = null;
    });

    final error = await ref.read(authControllerProvider.notifier).changePassword(
          currentPassword: current,
          newPassword: next,
        );
    if (!mounted) return;

    if (error != null) {
      setState(() {
        _pending = false;
        // The server's own wording, unedited: it already decides how much a
        // failure may say, and rephrasing it here is how a client starts
        // disclosing more than the server meant to.
        _errorMessage = error.userMessage;
      });
      return;
    }

    _currentController.clear();
    _newController.clear();
    _confirmController.clear();
    setState(() => _pending = false);
    // Every other session was revoked server-side, so the list below is stale
    // the instant this returns.
    ref.invalidate(authSessionsProvider);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Password changed. Your other devices were signed out.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final errorMessage = _errorMessage;

    return GlassCard(
      padding: EdgeInsets.all(context.space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CardHeader(
            icon: Icons.lock_outline,
            iconColor: context.colors.primary,
            title: 'Change password',
            description: 'Your other devices are signed out when the password '
                'changes. This one stays signed in.',
          ),
          SizedBox(height: context.space.lg),
          _PasswordField(
            key: const Key('security-current-password'),
            controller: _currentController,
            label: 'Current password',
            enabled: !_pending,
          ),
          SizedBox(height: context.space.md),
          _PasswordField(
            key: const Key('security-new-password'),
            controller: _newController,
            label: 'New password',
            enabled: !_pending,
          ),
          SizedBox(height: context.space.md),
          _PasswordField(
            key: const Key('security-confirm-password'),
            controller: _confirmController,
            label: 'Confirm new password',
            enabled: !_pending,
            onSubmitted: (_) => _submit(),
          ),
          if (errorMessage != null) ...[
            SizedBox(height: context.space.md),
            AuthError(message: errorMessage),
          ],
          SizedBox(height: context.space.lg),
          FilledButton(
            onPressed: _pending ? null : _submit,
            child: Text(_pending ? 'Updating…' : 'Update password'),
          ),
        ],
      ),
    );
  }
}

/// An obscured field with its own show/hide toggle, mirroring the sign-in and
/// registration forms. Owns nothing but the toggle — the text belongs to the
/// controller its parent disposes.
class _PasswordField extends StatefulWidget {
  const _PasswordField({
    required this.controller,
    required this.label,
    required this.enabled,
    this.onSubmitted,
    super.key,
  });

  final TextEditingController controller;
  final String label;
  final bool enabled;
  final ValueChanged<String>? onSubmitted;

  @override
  State<_PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<_PasswordField> {
  var _obscure = true;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: widget.controller,
      decoration: InputDecoration(
        labelText: widget.label,
        prefixIcon: const Icon(Icons.lock_outline),
        suffixIcon: IconButton(
          icon: Icon(
            _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
          ),
          tooltip: _obscure ? 'Show password' : 'Hide password',
          onPressed: () => setState(() => _obscure = !_obscure),
        ),
      ),
      obscureText: _obscure,
      autocorrect: false,
      enableSuggestions: false,
      enabled: widget.enabled,
      textInputAction: widget.onSubmitted == null
          ? TextInputAction.next
          : TextInputAction.done,
      onSubmitted: widget.onSubmitted,
    );
  }
}

// ── Sessions ─────────────────────────────────────────────────────────────

class _SessionsCard extends ConsumerWidget {
  const _SessionsCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sessionsAsync = ref.watch(authSessionsProvider);

    return GlassCard(
      padding: EdgeInsets.all(context.space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: _CardHeader(
                  icon: Icons.devices_outlined,
                  iconColor: context.colors.accent,
                  title: 'Where you are signed in',
                  description: 'Every device holding a live session on this '
                      'account. Sign out anything you do not recognise.',
                ),
              ),
              IconButton(
                icon: const Icon(Icons.refresh),
                tooltip: 'Refresh sessions',
                onPressed: () => ref.invalidate(authSessionsProvider),
              ),
            ],
          ),
          SizedBox(height: context.space.md),
          sessionsAsync.when(
            // Keep the list on screen while a revoke refetches, so the rows do
            // not blink out under the finger that just tapped one.
            skipLoadingOnReload: true,
            loading: () => const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: SkeletonBox(width: 220, height: 20),
            ),
            error: (error, _) => Text(
              error is AppError
                  ? error.userMessage
                  : "Couldn't load your sessions.",
              style: context.text.bodySm.copyWith(color: context.colors.danger),
            ),
            data: (sessions) => sessions.isEmpty
                ? Text(
                    'No active sessions.',
                    style:
                        context.text.bodySm.copyWith(color: context.colors.muted),
                  )
                : Column(
                    children: [
                      for (final session in sessions)
                        _SessionRow(session: session),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}

class _SessionRow extends ConsumerWidget {
  const _SessionRow({required this.session});

  final UserSession session;

  Future<void> _confirmRevoke(BuildContext context, WidgetRef ref) async {
    final label = sessionDeviceLabel(session.userAgent);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Sign out this device?'),
        content: Text('$label will have to sign in again to use the app.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: context.colors.danger,
            ),
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    final result =
        await ref.read(authRepositoryProvider).revokeSession(session.id);
    if (!context.mounted) return;
    // Refresh either way: a 404 means somebody else already revoked it, which
    // is still a list that no longer matches the screen.
    ref.invalidate(authSessionsProvider);
    result.fold(
      ok: (_) => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$label signed out.')),
      ),
      err: (error) => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.userMessage)),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ip = session.ipAddress;
    final subtitle = StringBuffer('Last used ${formatTimeAgo(session.lastUsedAt)}');
    if (ip != null && ip.isNotEmpty) subtitle.write(' · $ip');

    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        session.isCurrent ? Icons.smartphone_outlined : Icons.devices_other,
        color: session.isCurrent ? context.colors.primary : context.colors.muted,
      ),
      title: Row(
        children: [
          Flexible(
            child: Text(
              sessionDeviceLabel(session.userAgent),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.text.label,
            ),
          ),
          if (session.isCurrent) ...[
            SizedBox(width: context.space.sm),
            const _ThisDeviceBadge(),
          ],
        ],
      ),
      subtitle: Text(
        subtitle.toString(),
        style: context.text.caption.copyWith(color: context.colors.muted),
      ),
      // The current session deliberately has no revoke button: killing it from
      // here would leave the app holding a token the server has forgotten,
      // discovered only on the next request. Sign out — or Sign out everywhere
      // below — is the honest way to end this one, and both clean up locally.
      trailing: session.isCurrent
          ? null
          : IconButton(
              key: Key('revoke-session-${session.id}'),
              icon: Icon(Icons.logout, color: context.colors.danger, size: 20),
              tooltip: 'Sign out this device',
              onPressed: () => _confirmRevoke(context, ref),
            ),
    );
  }
}

class _ThisDeviceBadge extends StatelessWidget {
  const _ThisDeviceBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.space.sm,
        vertical: context.space.xxs,
      ),
      decoration: BoxDecoration(
        color: context.colors.primary.withAlpha(36),
        borderRadius: BorderRadius.circular(context.radii.full),
        border: Border.all(color: context.colors.primary.withAlpha(90)),
      ),
      child: Text(
        'This device',
        style: context.text.labelSm.copyWith(color: context.colors.primary),
      ),
    );
  }
}

// ── Sign out everywhere ──────────────────────────────────────────────────

class _SignOutEverywhereCard extends ConsumerStatefulWidget {
  const _SignOutEverywhereCard();

  @override
  ConsumerState<_SignOutEverywhereCard> createState() =>
      _SignOutEverywhereCardState();
}

class _SignOutEverywhereCardState
    extends ConsumerState<_SignOutEverywhereCard> {
  var _pending = false;

  Future<void> _confirm() async {
    if (_pending) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Sign out everywhere?'),
        content: const Text(
          'Every device — including this one — will have to sign in again. '
          'Downloaded chapters stay on this device.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: context.colors.danger,
            ),
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Sign out everywhere'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _pending = true);
    final error =
        await ref.read(authControllerProvider.notifier).logoutEverywhere();
    if (!mounted) return;
    setState(() => _pending = false);
    if (error != null) {
      // Nothing was revoked, and the local session is deliberately untouched:
      // the user can retry rather than be told "everywhere" about a call that
      // never landed.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.userMessage)),
      );
      return;
    }
    // This screen was pushed onto the navigator imperatively, so the router's
    // redirect to login rebuilds the pages *underneath* it — leaving a signed
    // out account still looking at its own security settings. Pop it here.
    await Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: EdgeInsets.all(context.space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CardHeader(
            icon: Icons.gpp_maybe_outlined,
            iconColor: context.colors.danger,
            title: 'Sign out everywhere',
            description: 'Revokes every session on the account, this device '
                'included. Downloaded chapters are left alone — clear those '
                'in Settings → Storage.',
          ),
          SizedBox(height: context.space.lg),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              foregroundColor: context.colors.danger,
            ),
            onPressed: _pending ? null : _confirm,
            icon: const Icon(Icons.logout, size: 18),
            label: Text(_pending ? 'Signing out…' : 'Sign out everywhere'),
          ),
        ],
      ),
    );
  }
}

// ── Shared bits ──────────────────────────────────────────────────────────

class _CardHeader extends StatelessWidget {
  const _CardHeader({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final Color iconColor;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: iconColor, size: 20),
            SizedBox(width: context.space.sm),
            Expanded(child: Text(title, style: context.text.h4)),
          ],
        ),
        SizedBox(height: context.space.sm),
        Text(
          description,
          style: context.text.bodySm
              .copyWith(color: context.colors.muted, height: 1.5),
        ),
      ],
    );
  }
}
