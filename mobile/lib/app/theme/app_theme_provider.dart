import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/preset_controller.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';

/// The live [ThemeData], derived once per real appearance change.
///
/// Hoisted out of `ManhwaManiacsApp.build` on purpose, because two ThemeData
/// built from byte-identical inputs are not `==`: [AppTheme.fromPalette]
/// builds five sub-themes from `WidgetStateProperty.resolveWith`, and the
/// object that returns declares no `operator ==`, so it falls back to
/// identity. MaterialApp wraps its child in an `AnimatedTheme`, which starts a
/// 200 ms `ThemeData.lerp` — ~100 fields, both ThemeExtensions included, and a
/// new `Theme` InheritedWidget published every frame — whenever the new
/// ThemeData differs from the old. Building it inside `build()` therefore
/// meant every unrelated root rebuild (the setup gate, the auth transition,
/// the profile-session gate — see `appRouterProvider`) animated the entire app
/// for 200 ms, at cold start and login, the frames that are already busiest.
///
/// This works because both inputs have stable identity: `AppPalettes` entries
/// are `static const` and `AppPresets` entries `static final`, so the provider
/// recomputes only when the user genuinely changes palette or preset and hands
/// back the same instance otherwise — at which point the lerp is what is
/// wanted.
final appThemeProvider = Provider<ThemeData>(
  (ref) => AppTheme.fromPalette(
    ref.watch(themeControllerProvider),
    metrics: ref.watch(presetControllerProvider),
  ),
  name: 'appTheme',
);
