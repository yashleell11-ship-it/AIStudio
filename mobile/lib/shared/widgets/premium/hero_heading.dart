import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Large Syne uppercase heading filled with a bronze→cream vertical gradient.
///
/// Mirrors the web `.hero-heading`: `linear-gradient(180deg,#9A8B7A,#E8DFD0)`
/// clipped to the text, uppercase, font-black, tight `leading-none` (height 1).
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

  /// Bronze → cream fill (top → bottom), matching web `.hero-heading`.
  static const LinearGradient _bronzeCream = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF9A8B7A), Color(0xFFE8DFD0)],
  );

  @override
  Widget build(BuildContext context) {
    // Responsive default: scale with available width, clamped to a sane range.
    final width = MediaQuery.sizeOf(context).width;
    final resolvedSize = fontSize ?? (width * 0.13).clamp(40.0, 72.0);

    final style = AppTypography.displayLg.copyWith(
      fontSize: resolvedSize,
      fontWeight: FontWeight.w800, // font-black
      height: 1.0, // leading-none
      letterSpacing: 0.5,
      color: Colors.white, // masked by the shader below
    );

    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (bounds) => _bronzeCream.createShader(bounds),
      child: Text(
        text.toUpperCase(),
        textAlign: textAlign,
        style: style,
      ),
    );
  }
}
