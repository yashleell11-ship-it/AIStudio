import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';

void main() {
  group('ScrollReveal', () {
    testWidgets('starts hidden then reveals when scrolled into view', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView.builder(
              itemCount: 2,
              itemBuilder: (context, index) {
                if (index == 0) {
                  return const SizedBox(height: 900);
                }
                return const ScrollReveal(
                  child: SizedBox(
                    height: 48,
                    child: Text('revealed'),
                  ),
                );
              },
            ),
          ),
        ),
      );

      await tester.pump();
      expect(find.text('revealed'), findsNothing);

      await tester.drag(find.byType(ListView), const Offset(0, -920));
      await tester.pump();

      final revealFinder = find.byType(ScrollReveal);
      expect(revealFinder, findsOneWidget);

      final opacityFinder = find.descendant(
        of: revealFinder,
        matching: find.byType(Opacity),
      );
      expect(tester.widget<Opacity>(opacityFinder).opacity, 0);

      await tester.pump(ScrollReveal.duration);

      expect(find.text('revealed'), findsOneWidget);
    });

    testWidgets('reveals immediately when not inside a scroll view', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ScrollReveal(
              child: Text('instant'),
            ),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(ScrollReveal.duration);

      expect(find.text('instant'), findsOneWidget);
    });
  });
}
