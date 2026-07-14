import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// A slow, continuously scrolling row of series covers — the mobile analogue of
/// the web `ScrollMarquee`.
///
/// The premium `ScrollMarquee` renders with `CachedNetworkImage`, which does
/// NOT attach the app's auth bearer token, so it cannot show the auth-gated
/// `/library/covers/*` routes. This widget instead auto-scrolls a row of
/// [SeriesCoverImage] tiles (which DO send the token), giving the same marquee
/// feel with covers that actually load.
///
/// Under reduced motion the auto-scroll is disabled and the row becomes a plain
/// manually-scrollable strip.
class HomeCoverMarquee extends StatefulWidget {
  const HomeCoverMarquee({
    super.key,
    required this.coverUrls,
    this.height = 168,
    this.reverse = false,
    this.pixelsPerSecond = 22,
  });

  /// Already-resolved (auth-gated) cover URLs to display as tiles.
  final List<String> coverUrls;

  final double height;

  /// Scroll direction — `true` drifts right-to-left.
  final bool reverse;

  final double pixelsPerSecond;

  @override
  State<HomeCoverMarquee> createState() => _HomeCoverMarqueeState();
}

class _HomeCoverMarqueeState extends State<HomeCoverMarquee> {
  final ScrollController _controller = ScrollController();
  Ticker? _ticker;
  Duration _lastElapsed = Duration.zero;
  bool _initialized = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Respect reduced motion: no ticker, the row is just manually scrollable.
      if (MediaQuery.disableAnimationsOf(context)) return;
      _ticker = Ticker(_onTick)..start();
    });
  }

  void _onTick(Duration elapsed) {
    if (!_controller.hasClients) return;
    final pos = _controller.position;
    if (pos.maxScrollExtent <= 0) {
      _lastElapsed = elapsed;
      return;
    }

    // The list is tripled, so one "set" is a third of the total content width.
    // We keep the offset parked in the middle set so there is always a full set
    // of covers on either side, then wrap seamlessly when it drifts past.
    final totalContent = pos.maxScrollExtent + pos.viewportDimension;
    final oneSet = totalContent / 3;

    if (!_initialized) {
      _initialized = true;
      _lastElapsed = elapsed;
      _controller.jumpTo(oneSet);
      return;
    }

    final dt = (elapsed - _lastElapsed).inMicroseconds / 1e6;
    _lastElapsed = elapsed;

    var next =
        _controller.offset + widget.pixelsPerSecond * dt * (widget.reverse ? -1 : 1);
    if (next >= oneSet * 2) {
      next -= oneSet;
    } else if (next < oneSet) {
      next += oneSet;
    }
    _controller.jumpTo(next.clamp(0.0, pos.maxScrollExtent));
  }

  @override
  void dispose() {
    _ticker?.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.coverUrls.isEmpty) return const SizedBox.shrink();

    final tileWidth = widget.height * (2 / 3);
    // Triple the covers so the loop is seamless in either direction.
    final looped = <String>[
      ...widget.coverUrls,
      ...widget.coverUrls,
      ...widget.coverUrls,
    ];
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    return SizedBox(
      height: widget.height,
      child: ListView.separated(
        controller: _controller,
        scrollDirection: Axis.horizontal,
        // Non-interactive while auto-scrolling; browsable under reduced motion.
        physics: reduceMotion
            ? const BouncingScrollPhysics()
            : const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
        itemCount: looped.length,
        separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.md),
        itemBuilder: (context, index) => SizedBox(
          width: tileWidth,
          height: widget.height,
          child: SeriesCoverImage(
            url: looped[index],
            width: tileWidth,
            height: widget.height,
            borderRadius: AppRadius.lg,
          ),
        ),
      ),
    );
  }
}
