import 'package:aistudio_mobile/app/router/app_router.dart';
import 'package:aistudio_mobile/app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AiStudioApp extends ConsumerWidget {
  const AiStudioApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'AIStudio',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      // AIStudio is dark-only — themeMode fixed to dark.
      themeMode: ThemeMode.dark,
      routerConfig: appRouter,
    );
  }
}
