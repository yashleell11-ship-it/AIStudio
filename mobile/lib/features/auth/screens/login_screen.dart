import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_header.dart';

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

  @override
  Widget build(BuildContext context) {
    final bootstrap = ref.watch(bootstrapStatusProvider);
    final needsBootstrap = bootstrap.valueOrNull?.needsBootstrap ?? false;
    final registrationEnabled =
        bootstrap.valueOrNull?.registrationEnabled ?? false;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: needsBootstrap
                  ? _buildBootstrapPrompt(context)
                  : _buildLoginForm(context, registrationEnabled),
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
        FilledButton(
          onPressed: () => context.go(Routes.register),
          child: const Text('Create the first account'),
        ),
      ],
    );
  }

  Widget _buildLoginForm(BuildContext context, bool registrationEnabled) {
    final errorMessage = _errorMessage;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const AuthHeader(
          title: 'Welcome back',
          subtitle: 'Sign in to your ManhwaManiacs account to continue.',
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
        FilledButton(
          onPressed: _pending ? null : _submit,
          child: _pending
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Sign in'),
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
