import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';

/// Frosted-glass panel: a backdrop blur behind a translucent warm-dark surface
/// with a subtle border and large rounded corners.
///
/// Mirrors the web `.glass-panel`: warm dark tint + `backdrop-blur`.
class GlassPanel extends StatelessWidget {
  const GlassPanel({
    super.key,
    required this.child,
    this.padding,
    this.borderRadius,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;

  /// Overrides the default `AppRadius.xl2` corner radius.
  final double? borderRadius;

  @override
  Widget build(BuildContext context) {
    final br = BorderRadius.circular(borderRadius ?? AppRadius.xl2);

    return ClipRRect(
      borderRadius: br,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: context.colors.surface.withValues(alpha: 0.7),
            borderRadius: br,
            border: Border.all(color: context.colors.border),
          ),
          // A transparent Material sits in front of the panel's background so
          // ListTile/SwitchListTile descendants paint their tint and ink on a
          // Material that isn't hidden by the panel's DecoratedBox color.
          child: Material(
            type: MaterialType.transparency,
            child: child,
          ),
        ),
      ),
    );
  }
}
