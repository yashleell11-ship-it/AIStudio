import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_header.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';

/// Sign-in screen. When the backend reports it still needs its first account
/// (`needs_bootstrap`) this instead guides the user to create the first
/// (admin) account.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  var _pending = false;
  var _obscurePassword = true;
  var _remember = true;
  String? _errorMessage;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_pending) return;
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    if (username.isEmpty || password.isEmpty) {
      setState(() => _errorMessage = 'Enter your username and password.');
      return;
    }

    setState(() {
      _pending = true;
      _errorMessage = null;
    });

    final error = await ref.read(authControllerProvider.notifier).login(
          username: username,
          password: password,
          remember: _remember,
        );
    if (!mounted) return;

    // On success the router redirect (watching authControllerProvider) routes
    // home and this screen is torn down, so no manual navigation is needed.
    if (error != null) {
      setState(() {
        _pending = false;
        _errorMessage = error.userMessage;
      });
    }
  }

  Future<void> _copyServerUrl(String baseUrl) async {
    await Clipboard.setData(ClipboardData(text: baseUrl));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Copied $baseUrl')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bootstrap = ref.watch(bootstrapStatusProvider);
    // Both read through the getters, not the raw flags: an empty users table
    // stops being claimable once the bootstrap window expires, and offering
    // the claim flow after that point walks the user into a rejection.
    final needsBootstrap = bootstrap.valueOrNull?.isBootstrapOpen ?? false;
    final registrationEnabled =
        bootstrap.valueOrNull?.isRegistrationOpen ?? false;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: GlassPanel(
                padding: const EdgeInsets.all(AppSpacing.xl2),
                child: needsBootstrap
                    ? _buildBootstrapPrompt(context)
                    : _buildLoginForm(context, registrationEnabled),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBootstrapPrompt(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const AuthHeader(
          title: 'Welcome to ManhwaManiacs',
          subtitle: 'This server has no accounts yet. Create the first account '
              '— it becomes the administrator.',
        ),
        const SizedBox(height: AppSpacing.xl2),
        PrimaryPillButton(
          label: 'Create the first account',
          expanded: true,
          onPressed: () => context.go(Routes.register),
        ),
      ],
    );
  }

  Widget _buildLoginForm(BuildContext context, bool registrationEnabled) {
    final errorMessage = _errorMessage;
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final serverHost = Uri.tryParse(baseUrl)?.host;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const AuthHeader(
          title: 'Welcome back',
          subtitle: 'Sign in to your ManhwaManiacs account to continue.',
        ),
        if (serverHost != null) ...[
          const SizedBox(height: AppSpacing.sm),
          // Tap to copy the full base URL — lets users share it with support
          // when a connection fails.
          GestureDetector(
            onTap: () => _copyServerUrl(baseUrl),
            behavior: HitTestBehavior.opaque,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Flexible(
                  child: Text(
                    'Server: $serverHost',
                    style:
                        AppTypography.caption.copyWith(color: context.colors.muted),
                  ),
                ),
                const SizedBox(width: AppSpacing.xs),
                Icon(
                  Icons.copy_outlined,
                  size: 14,
                  color: context.colors.muted,
                ),
              ],
            ),
          ),
        ],
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
          autocorrect: false,
          enableSuggestions: false,
          enabled: !_pending,
          onSubmitted: (_) => _submit(),
        ),
        const SizedBox(height: AppSpacing.sm),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Keep me signed in'),
          value: _remember,
          onChanged:
              _pending ? null : (value) => setState(() => _remember = value),
        ),
        if (errorMessage != null) ...[
          const SizedBox(height: AppSpacing.sm),
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
              label: _pending ? 'Signing in…' : 'Sign in',
              expanded: true,
              onPressed: _submit,
            ),
          ),
        ),
        if (registrationEnabled) ...[
          const SizedBox(height: AppSpacing.sm),
          TextButton(
            onPressed: _pending ? null : () => context.go(Routes.register),
            child: const Text('Create an account'),
          ),
        ],
      ],
    );
  }
}
