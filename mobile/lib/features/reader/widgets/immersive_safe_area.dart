import 'package:flutter/material.dart';

/// [SafeArea] for the one screen that hides the system overlays.
///
/// The reader enters [SystemUiMode.immersiveSticky] while a chapter is open,
/// which on iOS hides the status bar and the home indicator. When an overlay
/// is hidden the OS reports **no** inset for it, so `MediaQuery.padding`
/// collapses to zero — and `SafeArea` reads exactly that. The hardware does
/// not collapse with it: on a Dynamic Island device the cutout still covers
/// the top of the display, so a bar padded by `SafeArea` slides underneath it
/// and its buttons become unreachable. The same happens at the bottom against
/// the home-indicator strip.
///
/// `viewPadding` is the inset the display physically imposes, reported
/// whether or not the overlay is currently drawn — which is what a fullscreen
/// surface has to respect. This is deliberately NOT a general-purpose
/// replacement for [SafeArea]: everywhere the overlays are visible the two
/// agree, and `SafeArea` is the clearer statement of intent.
class ImmersiveSafeArea extends StatelessWidget {
  const ImmersiveSafeArea({
    super.key,
    this.top = true,
    this.bottom = true,
    required this.child,
  });

  final bool top;
  final bool bottom;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final insets = MediaQuery.viewPaddingOf(context);
    return Padding(
      padding: EdgeInsets.only(
        top: top ? insets.top : 0,
        bottom: bottom ? insets.bottom : 0,
        // Horizontal insets never collapse — nothing hides a landscape notch —
        // so they are honest on `viewPadding` and needed in landscape reading.
        left: insets.left,
        right: insets.right,
      ),
      child: child,
    );
  }
}
