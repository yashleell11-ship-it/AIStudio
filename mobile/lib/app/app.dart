import 'package:aistudio_mobile/app/router/app_router.dart';
import 'package:aistudio_mobile/app/theme/app_theme.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AiStudioApp extends ConsumerWidget {
  const AiStudioApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // AIStudio only ships a dark ThemeData today, so every ThemeMode
    // currently renders the same look. themeMode itself is wired to the
    // user's persisted Settings > Theme choice (System/Light/Dark) so the
    // preference takes effect immediately once a light theme is added.
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'AIStudio',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      darkTheme: AppTheme.dark,
      themeMode: themeMode,
      routerConfig: appRouter,
    );
  }
}
