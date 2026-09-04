import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:manhwamaniacs/app/theme/app_metrics.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

// Re-export both halves of the design system — the palette (colour) and the
// metrics (shape) — so callers can import just app_theme.dart.
export 'package:manhwamaniacs/app/theme/app_colors.dart';
export 'package:manhwamaniacs/app/theme/app_metrics.dart';
export 'package:manhwamaniacs/app/theme/app_palette.dart';
export 'package:manhwamaniacs/app/theme/app_palettes.dart';
export 'package:manhwamaniacs/app/theme/app_palettes.generated.dart';
export 'package:manhwamaniacs/app/theme/app_presets.dart';
export 'package:manhwamaniacs/app/theme/app_typography.dart';

/// ManhwaManiacs Material theme, built from any registered [AppPalette].
abstract final class AppTheme {
  /// System overlay (status bar / nav bar) style for the default palette.
  ///
  /// Kept for call sites that predate multi-theme; themed screens should use
  /// [overlayStyleFor] with the active palette instead.
  static const SystemUiOverlayStyle systemOverlayStyle = SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    statusBarBrightness: Brightness.dark,
    systemNavigationBarColor: Colors.transparent,
    systemNavigationBarIconBrightness: Brightness.light,
  );

  /// Overlay style matching [palette]'s brightness.
  ///
  /// The two brightness fields are inverted by design and read by different
  /// platforms. `statusBarIconBrightness` describes the *glyphs* and is
  /// Android-only; `statusBarBrightness` describes the *background behind* the
  /// bar and is the only field the iOS embedder looks at — it early-returns
  /// when that key is absent, which is why every AppBar's overlay style used
  /// to be a no-op on iPhone. Light palettes therefore need
  /// `statusBarBrightness: Brightness.light` (iOS shows dark glyphs) and
  /// `statusBarIconBrightness: Brightness.dark` (Android draws dark glyphs) —
  /// without this, light themes get invisible white status text.
  static SystemUiOverlayStyle overlayStyleFor(AppPalette palette) {
    final glyphs = palette.isDark ? Brightness.light : Brightness.dark;
    return SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: glyphs,
      statusBarBrightness: palette.brightness,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: glyphs,
    );
  }

  /// The default theme — Eclipse colour on Signature shape, what the app
  /// wore before either axis was selectable.
  static ThemeData get dark => fromPalette(AppPalettes.eclipse);

  /// Builds the app theme from a colour palette and a shape preset.
  ///
  /// [metrics] defaults to [AppPresets.signature] so the pre-preset call
  /// shape keeps working and keeps meaning what it meant. Both bundles ride
  /// on [ThemeData.extensions]: that is what makes `context.colors` and
  /// `context.space` reads rebuild when either axis changes.
  static ThemeData fromPalette(AppPalette p, {AppMetrics? metrics}) {
    final m = metrics ?? AppPresets.signature;
    final base =
        p.isDark ? const ColorScheme.dark() : const ColorScheme.light();
    final colorScheme = base.copyWith(
      surface: p.surface,
      onSurface: p.fg,
      primary: p.primary,
      onPrimary: p.primaryFg,
      secondary: p.accent,
      onSecondary: p.accentFg,
      error: p.danger,
      // Matches the pre-multi-theme choice: dark ink on the error fill for
      // the dark default, light ink for light palettes — [p.primaryFg] is
      // exactly that per-palette "ink on a filled control" tone.
      onError: p.primaryFg,
      outline: p.border,
      surfaceContainerHighest: p.surface2,
      scrim: p.scrim,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: p.brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: p.bg,
      canvasColor: p.surface,
      cardColor: p.surface,
      dividerColor: p.border,
      // Palette and metrics both ride on the ThemeData so `context.colors`
      // and `context.space` reads register a Theme dependency — that is the
      // entire repaint mechanism, for colour and for shape alike.
      extensions: [p, m],
      textTheme: m.text.textTheme.apply(
        bodyColor: p.fg,
        displayColor: p.fg,
      ),
      fontFamily: AppTypography.fontFamilyBody,

      // ── AppBar ────────────────────────────────────────────────────────────
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: p.fg,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        systemOverlayStyle: overlayStyleFor(p),
      ),

      // ── Navigation Bar (M3) ───────────────────────────────────────────────
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: p.sidebar,
        surfaceTintColor: Colors.transparent,
        shadowColor: Colors.transparent,
        elevation: 0,
        height: 56,
        indicatorColor: p.violetGlow,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.lg),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            size: 20,
            color: states.contains(WidgetState.selected) ? p.primary : p.muted,
          ),
        ),
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => m.text.labelSm.copyWith(
            fontSize: 10,
            fontWeight: FontWeight.w600,
            color: states.contains(WidgetState.selected) ? p.primary : p.muted,
          ),
        ),
      ),

      // ── Cards ─────────────────────────────────────────────────────────────
      cardTheme: CardThemeData(
        color: p.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.xl),
          side: BorderSide(color: p.border, width: m.strokes.border),
        ),
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
      ),

      // ── Buttons ───────────────────────────────────────────────────────────
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: p.primary,
          foregroundColor: p.primaryFg,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(m.radii.md),
          ),
          textStyle: m.text.labelLg,
          padding: EdgeInsets.symmetric(
            horizontal: m.space.xl,
            vertical: m.space.md,
          ),
          elevation: 0,
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: p.primary,
          side: BorderSide(color: p.primary, width: m.strokes.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(m.radii.md),
          ),
          textStyle: m.text.labelLg,
          padding: EdgeInsets.symmetric(
            horizontal: m.space.xl,
            vertical: m.space.md,
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: p.primary,
          textStyle: m.text.labelLg,
        ),
      ),

      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: p.muted,
        ),
      ),

      // ── Input ─────────────────────────────────────────────────────────────
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: p.surface2,
        hintStyle: m.text.body.copyWith(color: p.muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(m.radii.md),
          borderSide: BorderSide(color: p.border, width: m.strokes.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(m.radii.md),
          borderSide: BorderSide(color: p.border, width: m.strokes.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(m.radii.md),
          borderSide: BorderSide(color: p.primary, width: m.strokes.focus),
        ),
        contentPadding: EdgeInsets.symmetric(
          horizontal: m.space.lg,
          vertical: m.space.md,
        ),
      ),

      // ── Chips ─────────────────────────────────────────────────────────────
      chipTheme: ChipThemeData(
        backgroundColor: p.surface2,
        selectedColor: p.violetGlow,
        labelStyle: m.text.labelSm.copyWith(color: p.fg),
        side: BorderSide(color: p.border, width: m.strokes.border),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.full),
        ),
        padding: EdgeInsets.symmetric(
          horizontal: m.space.sm,
          vertical: m.space.xs,
        ),
      ),

      // ── Divider ───────────────────────────────────────────────────────────
      dividerTheme: DividerThemeData(
        color: p.border,
        thickness: m.strokes.divider,
        space: 0,
      ),

      // ── SnackBar ──────────────────────────────────────────────────────────
      snackBarTheme: SnackBarThemeData(
        backgroundColor: p.surfaceElevated,
        contentTextStyle: m.text.body.copyWith(color: p.fg),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.md),
        ),
        behavior: SnackBarBehavior.floating,
        elevation: 4,
      ),

      // ── Bottom Sheet ──────────────────────────────────────────────────────
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: p.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(m.radii.xl),
          ),
        ),
        elevation: 0,
      ),

      // ── Dialog ────────────────────────────────────────────────────────────
      dialogTheme: DialogThemeData(
        backgroundColor: p.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.xl2),
          side: BorderSide(color: p.border, width: m.strokes.border),
        ),
      ),

      // ── List Tiles ────────────────────────────────────────────────────────
      listTileTheme: ListTileThemeData(
        tileColor: Colors.transparent,
        selectedTileColor: p.violetGlow,
        selectedColor: p.primary,
        iconColor: p.muted,
        textColor: p.fg,
        contentPadding: EdgeInsets.symmetric(
          horizontal: m.space.xl2,
          vertical: m.space.xs,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.md),
        ),
      ),

      // ── Progress Indicator ────────────────────────────────────────────────
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: p.primary,
        linearTrackColor: p.surface2,
        circularTrackColor: p.surface2,
      ),

      // ── Switches / Checkboxes ─────────────────────────────────────────────
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? p.primary : p.muted,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (s) =>
              s.contains(WidgetState.selected) ? p.violetGlow : p.surface2,
        ),
      ),

      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? p.primary : p.surface2,
        ),
        checkColor: WidgetStateProperty.all(p.primaryFg),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(m.radii.xs),
        ),
        side: BorderSide(color: p.border, width: m.strokes.border),
      ),

      // ── Floating Action Button ────────────────────────────────────────────
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: p.primary,
        foregroundColor: p.primaryFg,
        elevation: 0,
      ),

      // ── Scrollbar ─────────────────────────────────────────────────────────
      scrollbarTheme: ScrollbarThemeData(
        thumbColor: WidgetStateProperty.all(p.muted.withAlpha(80)),
        radius: Radius.circular(m.radii.full),
        thickness: WidgetStateProperty.all(3),
      ),
    );
  }
}
