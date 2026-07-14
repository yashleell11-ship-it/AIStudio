import 'package:flutter/material.dart';

/// Translates [child] toward the pointer while it hovers/drags over the widget,
/// mirroring the web `Magnet` primitive.
///
/// On desktop/web the effect follows the mouse; on touch devices it responds to
/// a drag over the child and snaps back on release. Under reduced motion it is a
/// no-op that simply renders the child.
///
/// Unlike the web version — which inflates an invisible DOM hit region by
/// [padding] px — this implementation keeps detection inside the child's own
/// bounds so it never distorts page layout, and instead uses [padding] to clamp
/// the maximum pull distance so the effect stays bounded and robust.
class Magnet extends StatefulWidget {
  const Magnet({
    super.key,
    required this.child,
    this.strength = 3,
    this.padding = 150,
  });

  final Widget child;

  /// Divisor for the pull — higher = weaker magnet (matches web `strength`).
  final double strength;

  /// Upper bound (px) on how far the child can be pulled in any axis.
  final double padding;

  @override
  State<Magnet> createState() => _MagnetState();
}

class _MagnetState extends State<Magnet> {
  Offset _translation = Offset.zero;
  bool _active = false;

  void _updateFromLocal(Offset local, Size size) {
    if (size.isEmpty) return;
    // Vector from child center to the pointer, scaled down by strength and
    // clamped so a fast pointer can't fling the child arbitrarily far.
    final center = Offset(size.width / 2, size.height / 2);
    final delta = (local - center) / widget.strength;
    final max = widget.padding;
    setState(() {
      _active = true;
      _translation = Offset(
        delta.dx.clamp(-max, max),
        delta.dy.clamp(-max, max),
      );
    });
  }

  void _reset() {
    if (_translation == Offset.zero && !_active) return;
    setState(() {
      _active = false;
      _translation = Offset.zero;
    });
  }

  @override
  Widget build(BuildContext context) {
    // Reduced motion: no magnet behavior at all.
    if (MediaQuery.disableAnimationsOf(context)) return widget.child;

    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);

        return MouseRegion(
          onHover: (event) => _updateFromLocal(event.localPosition, size),
          onExit: (_) => _reset(),
          child: Listener(
            behavior: HitTestBehavior.translucent,
            onPointerMove: (event) =>
                _updateFromLocal(event.localPosition, size),
            onPointerUp: (_) => _reset(),
            onPointerCancel: (_) => _reset(),
            child: AnimatedContainer(
              // Active follows quickly; idle returns slowly (web .3s / .6s).
              duration: Duration(milliseconds: _active ? 300 : 600),
              curve: _active ? Curves.easeOut : Curves.easeInOut,
              transform: Matrix4.translationValues(
                _translation.dx,
                _translation.dy,
                0,
              ),
              transformAlignment: Alignment.center,
              child: widget.child,
            ),
          ),
        );
      },
    );
  }
}
