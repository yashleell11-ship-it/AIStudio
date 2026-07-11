import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';

/// Wraps a tappable surface with a subtle press-in scale so every tap feels
/// physical — the micro-interaction that separates a premium reader from a
/// stock one. A long-press additionally fires a light haptic tick.
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
    this.pressedScale = 0.97,
  });

  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// Scale applied while the pointer is held down.
  final double pressedScale;

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
        scale: _pressed ? widget.pressedScale : 1.0,
        duration: const Duration(milliseconds: 110),
        curve: Curves.easeOut,
        child: widget.child,
      ),
    );
  }
}
