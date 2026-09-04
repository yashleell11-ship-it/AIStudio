import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:manhwamaniacs/app/theme/app_palette.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

// Re-export the palette + colors + spacing + typography so callers can import
// just app_theme.dart.
export 'package:manhwamaniacs/app/theme/app_colors.dart';
export 'package:manhwamaniacs/app/theme/app_palette.dart';
export 'package:manhwamaniacs/app/theme/app_palettes.dart';
export 'package:manhwamaniacs/app/theme/app_spacing.dart';
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

  /// The default (Eclipse) theme — what the app wore before multi-theme.
  static ThemeData get dark => fromPalette(AppPalettes.eclipse);

  static ThemeData fromPalette(AppPalette p) {
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
      // The palette rides on the ThemeData so `context.colors` reads register
      // a Theme dependency — that is the entire repaint mechanism.
      extensions: [p],
      textTheme: AppTypography.textTheme.apply(
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
          borderRadius: BorderRadius.circular(AppRadius.lg),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            size: 20,
            color: states.contains(WidgetState.selected) ? p.primary : p.muted,
          ),
        ),
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => AppTypography.labelSm.copyWith(
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
          borderRadius: BorderRadius.circular(AppRadius.xl),
          side: BorderSide(color: p.border),
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
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          textStyle: AppTypography.labelLg,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl,
            vertical: AppSpacing.md,
          ),
          elevation: 0,
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: p.primary,
          side: BorderSide(color: p.primary),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          textStyle: AppTypography.labelLg,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl,
            vertical: AppSpacing.md,
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: p.primary,
          textStyle: AppTypography.labelLg,
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
        hintStyle: AppTypography.body.copyWith(color: p.muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: BorderSide(color: p.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: BorderSide(color: p.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: BorderSide(color: p.primary, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
      ),

      // ── Chips ─────────────────────────────────────────────────────────────
      chipTheme: ChipThemeData(
        backgroundColor: p.surface2,
        selectedColor: p.violetGlow,
        labelStyle: AppTypography.labelSm.copyWith(color: p.fg),
        side: BorderSide(color: p.border),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.full),
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
      ),

      // ── Divider ───────────────────────────────────────────────────────────
      dividerTheme: DividerThemeData(
        color: p.border,
        thickness: 1,
        space: 0,
      ),

      // ── SnackBar ──────────────────────────────────────────────────────────
      snackBarTheme: SnackBarThemeData(
        backgroundColor: p.surfaceElevated,
        contentTextStyle: AppTypography.body.copyWith(color: p.fg),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        behavior: SnackBarBehavior.floating,
        elevation: 4,
      ),

      // ── Bottom Sheet ──────────────────────────────────────────────────────
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: p.surface,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppRadius.xl),
          ),
        ),
        elevation: 0,
      ),

      // ── Dialog ────────────────────────────────────────────────────────────
      dialogTheme: DialogThemeData(
        backgroundColor: p.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.xl2),
          side: BorderSide(color: p.border),
        ),
      ),

      // ── List Tiles ────────────────────────────────────────────────────────
      listTileTheme: ListTileThemeData(
        tileColor: Colors.transparent,
        selectedTileColor: p.violetGlow,
        selectedColor: p.primary,
        iconColor: p.muted,
        textColor: p.fg,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xl2,
          vertical: AppSpacing.xs,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
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
          borderRadius: BorderRadius.circular(AppRadius.xs),
        ),
        side: BorderSide(color: p.border),
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
        radius: const Radius.circular(AppRadius.full),
        thickness: WidgetStateProperty.all(3),
      ),
    );
  }
}
