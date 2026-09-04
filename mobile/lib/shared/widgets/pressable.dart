import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// Wraps a tappable surface with a press-in scale so every tap feels physical
/// — the micro-interaction that separates a premium reader from a stock one. A
/// long-press additionally fires a light haptic tick.
///
/// How deep the press goes and how long it takes both come from the active
/// design preset's motion budget, so a preset that wants to feel calm gets a
/// calmer tap everywhere at once instead of screen by screen.
///
/// Use this for cover cards and other bare tap targets that don't already draw
/// an ink ripple. Surfaces that use [InkWell]/[GlassCard] ripples don't need
/// it.
class Pressable extends ConsumerStatefulWidget {
  const Pressable({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.pressedScale,
  });

  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// Scale applied while the pointer is held down. Null takes the design
  /// preset's press depth, which is the usual case — the quieter presets press
  /// less far, and Matte barely at all.
  final double? pressedScale;

  @override
  ConsumerState<Pressable> createState() => _PressableState();
}

class _PressableState extends ConsumerState<Pressable> {
  bool _pressed = false;

  void _setPressed(bool value) {
    if (_pressed != value) setState(() => _pressed = value);
  }

  @override
  Widget build(BuildContext context) {
    final motion = context.motion;
    return GestureDetector(
      onTapDown: (_) => _setPressed(true),
      onTapUp: (_) => _setPressed(false),
      onTapCancel: () => _setPressed(false),
      onTap: widget.onTap,
      onLongPress: widget.onLongPress == null
          ? null
          : () {
              ref.read(hapticsProvider).selection();
              widget.onLongPress!();
            },
      child: AnimatedScale(
        scale: _pressed
            ? (widget.pressedScale ?? motion.pressScale)
            : 1.0,
        duration: motion.scaled(const Duration(milliseconds: 110)),
        curve: Curves.easeOut,
        child: widget.child,
      ),
    );
  }
}
