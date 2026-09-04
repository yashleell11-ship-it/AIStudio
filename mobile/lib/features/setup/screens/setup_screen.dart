import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';

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
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: GlassPanel(
                padding: const EdgeInsets.all(AppSpacing.xl2),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Warm amber → ember brand mark.
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [context.colors.primary, context.colors.accent],
                        ),
                        borderRadius: BorderRadius.circular(AppRadius.lg),
                        boxShadow: [
                          BoxShadow(
                            color: context.colors.primary.withValues(alpha: 0.28),
                            blurRadius: 24,
                            spreadRadius: -4,
                          ),
                        ],
                      ),
                      child: Center(
                        child: Text(
                          'M',
                          style: AppTypography.h1.copyWith(color: Colors.white),
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xl2),
                    const HeroHeading(text: 'Get Started', fontSize: 38),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Connect to your ManhwaManiacs backend to browse, '
                      'download, and read.',
                      style:
                          AppTypography.body.copyWith(color: context.colors.muted),
                    ),
                    const SizedBox(height: AppSpacing.xl2),
                    TextField(
                      controller: _controller,
                      decoration: InputDecoration(
                        labelText: 'Server URL',
                        hintText: Env.defaultApiUrl,
                        prefixIcon: const Icon(Icons.dns_outlined),
                        errorText: _errorMessage,
                      ),
                      keyboardType: TextInputType.url,
                      enabled: !_pending,
                      onSubmitted: (_) => _continue(),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    // Warm CTA pill. `_continue` already no-ops while pending;
                    // the IgnorePointer + dimming just makes that visible.
                    IgnorePointer(
                      ignoring: _pending,
                      child: Opacity(
                        opacity: _pending ? 0.6 : 1,
                        child: PrimaryPillButton(
                          label: _pending ? 'Connecting…' : 'Continue',
                          expanded: true,
                          onPressed: _continue,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
