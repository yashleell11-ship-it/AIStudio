import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/utils/register_error_message.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_header.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';

/// Account creation screen. On a fresh instance (`needs_bootstrap`) the account
/// created here becomes the administrator and needs no invite code; otherwise
/// it is a normal account, only reachable when self-service registration is
/// enabled, and gated by an invite code when the server asks for one.
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _inviteCodeController = TextEditingController();
  final _displayNameController = TextEditingController();
  final _emailController = TextEditingController();

  var _pending = false;
  var _obscurePassword = true;
  var _obscureConfirmPassword = true;
  String? _errorMessage;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _inviteCodeController.dispose();
    _displayNameController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  String? _validate(
    String username,
    String password,
    String confirmPassword,
    String email, {
    required bool inviteCodeRequired,
    required String inviteCode,
  }) {
    if (username.isEmpty || password.isEmpty) {
      return 'Choose a username and password.';
    }
    if (password.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (password != confirmPassword) {
      return "Passwords don't match.";
    }
    if (inviteCodeRequired && inviteCode.isEmpty) {
      return 'Enter the invite code for this server.';
    }
    if (email.isNotEmpty && !email.contains('@')) {
      return 'Enter a valid email address, or leave it blank.';
    }
    return null;
  }

  Future<void> _submit() async {
    if (_pending) return;
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    final confirmPassword = _confirmPasswordController.text;
    final inviteCode = _inviteCodeController.text.trim();
    final displayName = _displayNameController.text.trim();
    final email = _emailController.text.trim();

    final status = ref.read(bootstrapStatusProvider).valueOrNull;
    final needsBootstrap = status?.isBootstrapOpen ?? false;
    // The bootstrap account never needs an invite code, regardless of what the
    // flag says — but only while the window is genuinely open. Once it shuts,
    // this is an ordinary registration and the code applies again.
    final inviteCodeRequired =
        !needsBootstrap && (status?.inviteCodeRequired ?? false);

    final validationError = _validate(
      username,
      password,
      confirmPassword,
      email,
      inviteCodeRequired: inviteCodeRequired,
      inviteCode: inviteCode,
    );
    if (validationError != null) {
      setState(() => _errorMessage = validationError);
      return;
    }

    setState(() {
      _pending = true;
      _errorMessage = null;
    });

    final error = await ref.read(authControllerProvider.notifier).register(
          username: username,
          password: password,
          email: email.isEmpty ? null : email,
          displayName: displayName.isEmpty ? null : displayName,
          inviteCode: inviteCode.isEmpty ? null : inviteCode,
          remember: true,
        );
    if (!mounted) return;

    // On success the router redirect routes home and this screen is torn down.
    if (error != null) {
      setState(() {
        _pending = false;
        _errorMessage = registerErrorMessage(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(bootstrapStatusProvider).valueOrNull;
    final needsBootstrap = status?.isBootstrapOpen ?? false;
    final registrationClosed = status != null &&
        !status.isBootstrapOpen &&
        !status.isRegistrationOpen;
    final inviteCodeRequired =
        !needsBootstrap && (status?.inviteCodeRequired ?? false);

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.login)),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: GlassPanel(
                padding: const EdgeInsets.all(AppSpacing.xl2),
                child: registrationClosed
                    ? _buildClosed(context)
                    : _buildForm(
                        context,
                        needsBootstrap: needsBootstrap,
                        inviteCodeRequired: inviteCodeRequired,
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildClosed(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const AuthHeader(
          title: 'Registration closed',
          subtitle: 'This server is not accepting new accounts right now. Ask '
              'an administrator for access.',
        ),
        const SizedBox(height: AppSpacing.xl2),
        PrimaryPillButton(
          label: 'Back to sign in',
          expanded: true,
          onPressed: () => context.go(Routes.login),
        ),
      ],
    );
  }

  Widget _buildForm(
    BuildContext context, {
    required bool needsBootstrap,
    required bool inviteCodeRequired,
  }) {
    final errorMessage = _errorMessage;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AuthHeader(
          title: needsBootstrap ? 'Claim this server' : 'Join ManhwaManiacs',
          subtitle: needsBootstrap
              ? 'This server has no accounts yet. The account you create here '
                  'becomes the administrator.'
              : 'Create your ManhwaManiacs account to get started.',
        ),
        const SizedBox(height: AppSpacing.xl2),
        TextField(
          controller: _usernameController,
          decoration: const InputDecoration(
            labelText: 'Username',
            prefixIcon: Icon(Icons.person_outline),
          ),
          textInputAction: TextInputAction.next,
          autocorrect: false,
          enableSuggestions: false,
          enabled: !_pending,
        ),
        const SizedBox(height: AppSpacing.lg),
        TextField(
          controller: _passwordController,
          decoration: InputDecoration(
            labelText: 'Password',
            helperText: 'At least 8 characters',
            prefixIcon: const Icon(Icons.lock_outline),
            suffixIcon: IconButton(
              icon: Icon(
                _obscurePassword
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
              ),
              tooltip: _obscurePassword ? 'Show password' : 'Hide password',
              onPressed: () =>
                  setState(() => _obscurePassword = !_obscurePassword),
            ),
          ),
          obscureText: _obscurePassword,
          textInputAction: TextInputAction.next,
          autocorrect: false,
          enableSuggestions: false,
          enabled: !_pending,
        ),
        const SizedBox(height: AppSpacing.lg),
        TextField(
          controller: _confirmPasswordController,
          decoration: InputDecoration(
            labelText: 'Confirm password',
            prefixIcon: const Icon(Icons.lock_outline),
            suffixIcon: IconButton(
              icon: Icon(
                _obscureConfirmPassword
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
              ),
              tooltip:
                  _obscureConfirmPassword ? 'Show password' : 'Hide password',
              onPressed: () => setState(
                () => _obscureConfirmPassword = !_obscureConfirmPassword,
              ),
            ),
          ),
          obscureText: _obscureConfirmPassword,
          textInputAction: inviteCodeRequired
              ? TextInputAction.next
              : TextInputAction.done,
          autocorrect: false,
          enableSuggestions: false,
          enabled: !_pending,
          onSubmitted: inviteCodeRequired ? null : (_) => _submit(),
        ),
        // The invite-code gate. Never shown while bootstrapping — the first
        // account on a fresh server never needs one — and otherwise only when
        // the server's bootstrap-status probe says it requires one.
        if (inviteCodeRequired) ...[
          const SizedBox(height: AppSpacing.lg),
          TextField(
            controller: _inviteCodeController,
            decoration: const InputDecoration(
              labelText: 'Invite code',
              prefixIcon: Icon(Icons.vpn_key_outlined),
            ),
            textInputAction: TextInputAction.done,
            autocorrect: false,
            enableSuggestions: false,
            enabled: !_pending,
            onSubmitted: (_) => _submit(),
          ),
        ],
        const SizedBox(height: AppSpacing.lg),
        TextField(
          controller: _displayNameController,
          decoration: const InputDecoration(
            labelText: 'Display name (optional)',
            prefixIcon: Icon(Icons.badge_outlined),
          ),
          textInputAction: TextInputAction.next,
          enabled: !_pending,
        ),
        const SizedBox(height: AppSpacing.lg),
        TextField(
          controller: _emailController,
          decoration: const InputDecoration(
            labelText: 'Email (optional)',
            prefixIcon: Icon(Icons.mail_outline),
          ),
          keyboardType: TextInputType.emailAddress,
          autocorrect: false,
          enableSuggestions: false,
          enabled: !_pending,
          onSubmitted: (_) => _submit(),
        ),
        if (errorMessage != null) ...[
          const SizedBox(height: AppSpacing.lg),
          AuthError(message: errorMessage),
        ],
        const SizedBox(height: AppSpacing.lg),
        // Warm CTA pill. `_submit` already no-ops while pending; the
        // IgnorePointer + dimming just makes that visually clear.
        IgnorePointer(
          ignoring: _pending,
          child: Opacity(
            opacity: _pending ? 0.6 : 1,
            child: PrimaryPillButton(
              label: _pending
                  ? 'Creating account…'
                  : (needsBootstrap
                      ? 'Create the administrator account'
                      : 'Create account'),
              expanded: true,
              onPressed: _submit,
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        TextButton(
          onPressed: _pending ? null : () => context.go(Routes.login),
          child: const Text('I already have an account'),
        ),
      ],
    );
  }
}
