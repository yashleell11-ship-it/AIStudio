import 'package:flutter/material.dart';

/// Fades + translates [child] into view on first build.
///
/// Mirrors the web `FadeIn` premium primitive: the child starts slightly
/// offset and transparent, then eases to its resting position on mount.
/// Honors reduced motion by rendering the child immediately with no animation.
class FadeIn extends StatefulWidget {
  const FadeIn({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.offset = const Offset(0, 30),
    this.duration = const Duration(milliseconds: 700),
  });

  final Widget child;

  /// Delay before the animation starts (matches web `delay` prop).
  final Duration delay;

  /// Initial translation the child animates FROM, toward `Offset.zero`.
  final Offset offset;

  /// Total animation duration.
  final Duration duration;

  /// Ease curve mirroring the web `[0.25, 0.1, 0.25, 1]` cubic-bezier.
  static const Cubic curve = Cubic(0.25, 0.1, 0.25, 1);

  @override
  State<FadeIn> createState() => _FadeInState();
}

class _FadeInState extends State<FadeIn> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _translate;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.duration);
    final curved = CurvedAnimation(parent: _controller, curve: FadeIn.curve);
    _opacity = Tween<double>(begin: 0, end: 1).animate(curved);
    _translate = Tween<Offset>(begin: widget.offset, end: Offset.zero)
        .animate(curved);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (MediaQuery.disableAnimationsOf(context)) {
        _controller.value = 1;
        return;
      }
      if (widget.delay == Duration.zero) {
        _controller.forward();
      } else {
        Future<void>.delayed(widget.delay, () {
          if (mounted) _controller.forward();
        });
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Reduced motion: render child immediately, no wrapper animation.
    if (MediaQuery.disableAnimationsOf(context)) return widget.child;
    if (_controller.isCompleted) return widget.child;

    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) => Opacity(
          opacity: _opacity.value.clamp(0.0, 1.0),
          child: Transform.translate(offset: _translate.value, child: child),
        ),
        child: widget.child,
      ),
    );
  }
}
