import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/settings/screens/diagnostics_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('DiagnosticsScreen renders all sections', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: DiagnosticsScreen()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Diagnostics'), findsOneWidget);
    expect(find.text('RENDERING PERFORMANCE'), findsOneWidget);
    expect(find.text('DISPLAY'), findsOneWidget);
    expect(find.text('DEVICE'), findsOneWidget);
    expect(find.text('IMAGE CACHE'), findsOneWidget);
  });
}
