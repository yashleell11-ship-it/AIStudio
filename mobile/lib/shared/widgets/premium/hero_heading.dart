import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_palettes.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Large Syne uppercase heading filled with a vertical gradient from the
/// palette's accent into its body colour.
///
/// Mirrors the web `.hero-heading`: `linear-gradient(180deg, var(--mm-hero-from),
/// var(--mm-hero-to))` clipped to the text, uppercase, font-black, tight
/// `leading-none` (height 1).
///
/// The stops were a literal `#9A8B7A → #E8DFD0` — Eclipse's bronze-and-cream —
/// which put Eclipse's title above every other palette's app, including on the
/// login screen, where the theme key does not exist yet and the app can only
/// paint its default.
class HeroHeading extends StatelessWidget {
  const HeroHeading({
    super.key,
    required this.text,
    this.fontSize,
    this.textAlign,
  });

  final String text;

  /// Overrides the responsive default size.
  final double? fontSize;

  final TextAlign? textAlign;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final fill = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: [colors.heroFrom, colors.heroTo],
    );
    // Responsive default: scale with available width, clamped to a sane range.
    final width = MediaQuery.sizeOf(context).width;
    final resolvedSize = fontSize ?? (width * 0.13).clamp(40.0, 72.0);

    final style = context.text.displayLg.copyWith(
      fontSize: resolvedSize,
      fontWeight: FontWeight.w800, // font-black
      height: 1.0, // leading-none
      letterSpacing: 0.5,
      color: Colors.white, // masked by the shader below
    );

    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: fill.createShader,
      child: Text(
        text.toUpperCase(),
        textAlign: textAlign,
        style: style,
      ),
    );
  }
}
