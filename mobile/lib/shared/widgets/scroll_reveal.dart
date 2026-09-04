import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Reveals [child] with a subtle fade + upward slide the first time it enters
/// the nearest scroll viewport.
///
/// Designed for lazy [ListView]/[GridView] builders: each item listens to
/// scroll only until it has animated once, then renders as a plain [child].
///
/// The active design preset decides whether the reveal happens at all and how
/// fast: presets that want to feel like a tool rather than a showcase turn it
/// off, in which case this collapses to the bare [child] and never attaches a
/// scroll listener. The geometry below is animation, not layout rhythm, so it
/// is stated in plain pixels rather than read from the spacing scale — a
/// denser preset should not slide its rows a shorter distance.
class ScrollReveal extends StatefulWidget {
  const ScrollReveal({
    super.key,
    required this.child,
    this.index,
  });

  final Widget child;

  /// Optional list index for a capped stagger so rows feel sequenced, not
  /// synchronized.
  final int? index;

  static const Duration duration = Duration(milliseconds: 260);

  /// How far the item slides up from, in pixels.
  static const double slideOffset = 8;

  /// How far outside the viewport an item starts animating, in pixels.
  static const double viewportLead = 32;

  /// Milliseconds between staggered neighbours.
  static const int staggerStepMs = 24;

  @override
  State<ScrollReveal> createState() => _ScrollRevealState();
}

class _ScrollRevealState extends State<ScrollReveal>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;

  ScrollPosition? _scrollPosition;
  VoidCallback? _scrollListener;
  bool _revealed = false;

  Duration get _staggerDelay {
    final index = widget.index;
    if (index == null) return Duration.zero;
    final step = context.motion.scaled(
      const Duration(milliseconds: ScrollReveal.staggerStepMs),
    );
    return step * (index % 5);
  }

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: ScrollReveal.duration);
    final curve = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
    _opacity = Tween<double>(begin: 0, end: 1).animate(curve);
    _slide = Tween<Offset>(
      begin: const Offset(0, ScrollReveal.slideOffset),
      end: Offset.zero,
    ).animate(curve);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _attachScrollListener();
      _maybeReveal();
    });
  }

  @override
  void dispose() {
    _detachScrollListener();
    _controller.dispose();
    super.dispose();
  }

  void _attachScrollListener() {
    if (_revealed || _scrollListener != null) return;

    final scrollable = Scrollable.maybeOf(context);
    if (scrollable == null) {
      _startReveal();
      return;
    }

    _scrollPosition = scrollable.position;
    _scrollListener = _maybeReveal;
    _scrollPosition!.addListener(_scrollListener!);
  }

  void _detachScrollListener() {
    if (_scrollPosition != null && _scrollListener != null) {
      _scrollPosition!.removeListener(_scrollListener!);
    }
    _scrollPosition = null;
    _scrollListener = null;
  }

  void _maybeReveal() {
    if (_revealed || !mounted) return;
    if (!_isInViewport()) return;
    _startReveal();
  }

  void _startReveal() {
    if (_revealed || !mounted) return;
    _revealed = true;
    _detachScrollListener();
    // Set here rather than in initState: the duration comes from the preset,
    // and Theme.of is only safe once dependencies are resolved.
    _controller.duration = context.motion.scaled(ScrollReveal.duration);

    final delay = _staggerDelay;
    if (delay == Duration.zero) {
      _controller.forward();
      return;
    }

    Future<void>.delayed(delay, () {
      if (mounted && !_controller.isCompleted) {
        _controller.forward();
      }
    });
  }

  bool _isInViewport() {
    final target = context.findRenderObject();
    if (target is! RenderBox || !target.hasSize) return false;

    final scrollable = Scrollable.maybeOf(context);
    if (scrollable == null) return true;

    final viewport = RenderAbstractViewport.maybeOf(target);
    if (viewport == null) return true;

    final reveal = viewport.getOffsetToReveal(target, 0);
    final pixels = scrollable.position.pixels;
    final extent = scrollable.position.viewportDimension;
    const lead = ScrollReveal.viewportLead;

    final itemTop = reveal.offset;
    final itemBottom = itemTop + target.size.height;

    return itemBottom > pixels - lead && itemTop < pixels + extent + lead;
  }

  @override
  Widget build(BuildContext context) {
    if (_controller.isCompleted) return widget.child;
    // A preset that has switched the reveal off renders the item plainly. The
    // controller is still constructed (so the widget can be rebuilt into a
    // preset that wants it) but is never driven.
    if (!context.motion.scrollReveal) return widget.child;

    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Opacity(
            opacity: _opacity.value,
            child: Transform.translate(
              offset: _slide.value,
              child: child,
            ),
          );
        },
        child: widget.child,
      ),
    );
  }
}
