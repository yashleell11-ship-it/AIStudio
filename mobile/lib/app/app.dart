import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_lifecycle_gate.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_auto_show.dart';

class ManhwaManiacsApp extends ConsumerWidget {
  const ManhwaManiacsApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // The active palette drives the whole look: ThemeData (Material widgets),
    // the AppPalette extension (context.colors reads), and the system bars.
    final palette = ref.watch(themeControllerProvider);
    final themed = AppTheme.fromPalette(palette);
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'ManhwaManiacs',
      debugShowCheckedModeBanner: false,
      // Same ThemeData on both slots: the in-app theme gallery (not the OS
      // light/dark toggle) owns the choice, including light palettes.
      theme: themed,
      darkTheme: themed,
      routerConfig: router,
      // Baseline overlay style for the screens that have no AppBar to publish
      // one — the dashboard, the reader, the profile picker. Without it those
      // screens inherit whatever the last AppBar happened to set, which on iOS
      // means falling back to `UIStatusBarStyleDefault` (dark glyphs when the
      // phone is in Light appearance) over the app's near-black background.
      // Any AppBar's own AnnotatedRegion sits deeper in the tree and still
      // wins. Derived from the palette so light themes get dark status-bar
      // glyphs instead of invisible white ones.
      builder: (context, child) => AnnotatedRegion<SystemUiOverlayStyle>(
        value: AppTheme.overlayStyleFor(palette),
        child: DownloadsLifecycleGate(
          child: WhatsNewAutoShow(child: child ?? const SizedBox.shrink()),
        ),
      ),
    );
  }
}