import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/display/high_refresh_rate.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/app_theme_provider.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_lifecycle_gate.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_auto_show.dart';

class ManhwaManiacsApp extends ConsumerWidget {
  const ManhwaManiacsApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // The two design axes drive the whole look between them: the palette is
    // colour (context.colors, the system bars) and the preset is shape
    // (context.space / radii / text / surfaces). Both land on one ThemeData,
    // so changing either rebuilds the tree through MaterialApp's own
    // AnimatedTheme — which is why neither needs a restart to apply. The
    // ThemeData is built in `appThemeProvider` rather than here so that a root
    // rebuild for some *other* reason hands back the same instance and starts
    // no animation; see that provider for why identity is what matters.
    final palette = ref.watch(themeControllerProvider);
    final themed = ref.watch(appThemeProvider);
    final router = ref.watch(appRouterProvider);
    // Keeps the window's display-mode preference in step with the user's
    // setting for as long as the app is up.
    ref.watch(highRefreshRateSyncProvider);

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