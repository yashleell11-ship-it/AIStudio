import 'package:flutter/widgets.dart';

/// Breakpoints matching the ManhwaManiacs frontend Tailwind config.
abstract final class Breakpoints {
  static const double mobile = 768;
  static const double tablet = 1024;
  static const double desktop = 1280;
}

/// Resolved device class for the current viewport.
enum DeviceClass { mobile, tablet, desktop }

extension ResponsiveContext on BuildContext {
  double get screenWidth => MediaQuery.sizeOf(this).width;
  double get screenHeight => MediaQuery.sizeOf(this).height;

  DeviceClass get deviceClass {
    final w = screenWidth;
    if (w < Breakpoints.mobile) return DeviceClass.mobile;
    if (w < Breakpoints.tablet) return DeviceClass.tablet;
    return DeviceClass.desktop;
  }

  bool get isMobile => deviceClass == DeviceClass.mobile;
  bool get isTablet => deviceClass == DeviceClass.tablet;
  bool get isDesktop => deviceClass == DeviceClass.desktop;
  bool get isWideScreen => screenWidth >= Breakpoints.tablet;

  /// Number of grid columns for a series grid at this viewport width.
  int get seriesGridColumns {
    final w = screenWidth;
    if (w < 400) return 2;
    if (w < Breakpoints.mobile) return 3;
    if (w < Breakpoints.tablet) return 4;
    if (w < Breakpoints.desktop) return 5;
    return 6;
  }
}

/// Builds a different widget depending on device class.
class Responsive extends StatelessWidget {
  const Responsive({
    super.key,
    required this.mobile,
    this.tablet,
    this.desktop,
  });

  final Widget mobile;
  final Widget? tablet;
  final Widget? desktop;

  @override
  Widget build(BuildContext context) {
    return switch (context.deviceClass) {
      DeviceClass.desktop => desktop ?? tablet ?? mobile,
      DeviceClass.tablet => tablet ?? mobile,
      DeviceClass.mobile => mobile,
    };
  }
}
