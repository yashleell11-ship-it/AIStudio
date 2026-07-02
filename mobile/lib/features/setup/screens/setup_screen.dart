import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/config/env.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SetupScreen extends ConsumerStatefulWidget {
  const SetupScreen({super.key});

  @override
  ConsumerState<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends ConsumerState<SetupScreen> {
  late final TextEditingController _controller;
  var _pending = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: Env.defaultApiUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _continue() async {
    if (_pending) return;
    setState(() {
      _pending = true;
      _errorMessage = null;
    });

    final error =
        await ref.read(settingsActionsProvider).validateAndSaveApiUrl(_controller.text);
    if (!mounted) return;

    if (error != null) {
      setState(() {
        _pending = false;
        _errorMessage = error.userMessage;
      });
      return;
    }

    context.go(Routes.library);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          children: [
            Text('Welcome to AIStudio', style: AppTypography.h2),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'Connect to your AIStudio backend to browse, download, and read.',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            const SizedBox(height: AppSpacing.xl2),
            TextField(
              controller: _controller,
              decoration: InputDecoration(
                labelText: 'Server URL',
                hintText: Env.defaultApiUrl,
                errorText: _errorMessage,
              ),
              keyboardType: TextInputType.url,
              enabled: !_pending,
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(
              onPressed: _pending ? null : _continue,
              child: _pending
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Continue'),
            ),
          ],
        ),
      ),
    );
  }
}
