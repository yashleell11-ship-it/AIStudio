import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';

/// Reveals [child] with a subtle fade + upward slide the first time it enters
/// the nearest scroll viewport.
///
/// Designed for lazy [ListView]/[GridView] builders: each item listens to
/// scroll only until it has animated once, then renders as a plain [child].
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
  static const double slideOffset = AppSpacing.sm;
  static const double viewportLead = AppSpacing.xl3;

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
    final stepMs = (context.space.md * 2).toInt();
    return Duration(milliseconds: (index % 5) * stepMs);
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
