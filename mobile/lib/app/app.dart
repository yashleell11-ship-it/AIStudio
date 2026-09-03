import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_lifecycle_gate.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_auto_show.dart';

class ManhwaManiacsApp extends ConsumerWidget {
  const ManhwaManiacsApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'ManhwaManiacs',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      darkTheme: AppTheme.dark,
      themeMode: themeMode,
      routerConfig: router,
      // Baseline overlay style for the screens that have no AppBar to publish
      // one — the dashboard, the reader, the profile picker. Without it those
      // screens inherit whatever the last AppBar happened to set, which on iOS
      // means falling back to `UIStatusBarStyleDefault` (dark glyphs when the
      // phone is in Light appearance) over the app's near-black background.
      // Any AppBar's own AnnotatedRegion sits deeper in the tree and still wins.
      builder: (context, child) => AnnotatedRegion<SystemUiOverlayStyle>(
        value: AppTheme.systemOverlayStyle,
        child: DownloadsLifecycleGate(
          child: WhatsNewAutoShow(child: child ?? const SizedBox.shrink()),
        ),
      ),
    );
  }
}