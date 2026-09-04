import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/widgets/immersive_safe_area.dart';

/// The reader hides the system overlays, and a hidden overlay reports **no**
/// inset — `MediaQuery.padding` goes to zero while the Dynamic Island keeps
/// physically covering the top of the display. These pump exactly that
/// combination: zero `padding`, real `viewPadding`. A `SafeArea` here pads by
/// nothing and puts the back button under the cutout, which is the bug.
Widget _wrap({
  required EdgeInsets padding,
  required EdgeInsets viewPadding,
  required Widget child,
}) {
  return MediaQuery(
    data: MediaQueryData(padding: padding, viewPadding: viewPadding),
    child: Directionality(textDirection: TextDirection.ltr, child: child),
  );
}

void main() {
  const islandInset = EdgeInsets.only(top: 59, bottom: 34);

  testWidgets('insets the child even when the hidden overlays report no padding',
      (tester) async {
    await tester.pumpWidget(_wrap(
      padding: EdgeInsets.zero,
      viewPadding: islandInset,
      child: ImmersiveSafeArea(child: Container(key: const Key('bar'))),
    ),);

    expect(tester.getTopLeft(find.byKey(const Key('bar'))).dy, 59);
    expect(
      tester.getBottomLeft(find.byKey(const Key('bar'))).dy,
      600 - 34,
      reason: 'the home-indicator strip collapses the same way the status bar does',
    );
  });

  testWidgets('honours top/bottom opt-outs so each bar takes only its own edge',
      (tester) async {
    await tester.pumpWidget(_wrap(
      padding: EdgeInsets.zero,
      viewPadding: islandInset,
      child: ImmersiveSafeArea(
        bottom: false,
        child: Container(key: const Key('top-bar')),
      ),
    ),);

    expect(tester.getTopLeft(find.byKey(const Key('top-bar'))).dy, 59);
    expect(tester.getBottomLeft(find.byKey(const Key('top-bar'))).dy, 600);
  });

  testWidgets('agrees with SafeArea when the overlays are visible',
      (tester) async {
    // Nothing is hidden here, so both properties report the same inset and this
    // must not double-pad — the widget is a fix for one screen, not a new
    // layout rule.
    await tester.pumpWidget(_wrap(
      padding: islandInset,
      viewPadding: islandInset,
      child: ImmersiveSafeArea(child: Container(key: const Key('bar'))),
    ),);

    expect(tester.getTopLeft(find.byKey(const Key('bar'))).dy, 59);
  });
}
