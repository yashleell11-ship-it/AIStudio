import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/settings/models/backup_status.dart';
import 'package:manhwamaniacs/features/settings/providers/backup_provider.dart';
import 'package:manhwamaniacs/features/settings/repositories/backup_repository.dart';
import 'package:manhwamaniacs/features/settings/screens/backup_screen.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

class _FakeBackupRepository implements BackupRepository {
  _FakeBackupRepository({this.restorePending = false, this.statusError});

  bool restorePending;
  AppError? statusError;
  int cancelCallCount = 0;
  int importCallCount = 0;
  String? lastImportedPath;

  @override
  Future<Result<BackupStatus>> getStatus() async {
    if (statusError != null) return Err(statusError!);
    return Ok(BackupStatus(restorePending: restorePending));
  }

  @override
  Future<Result<void>> importBackup(String filePath) async {
    importCallCount++;
    lastImportedPath = filePath;
    restorePending = true;
    return const Ok(null);
  }

  @override
  Future<Result<void>> cancelPendingRestore() async {
    cancelCallCount++;
    restorePending = false;
    return const Ok(null);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('backupStatusProvider', () {
    test('resolves the repository status', () async {
      final container = ProviderContainer(
        overrides: [
          backupRepositoryProvider.overrideWithValue(
            _FakeBackupRepository(restorePending: true),
          ),
        ],
      );
      addTearDown(container.dispose);

      final status = await container.read(backupStatusProvider.future);
      expect(status.restorePending, isTrue);
    });

    test('degrades to "nothing pending" when the repository errors', () async {
      final container = ProviderContainer(
        overrides: [
          backupRepositoryProvider.overrideWithValue(
            _FakeBackupRepository(
              statusError: const NetworkError(message: 'offline'),
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final status = await container.read(backupStatusProvider.future);
      expect(status.restorePending, isFalse);
    });
  });

  Widget wrap(BackupRepository repo) {
    return ProviderScope(
      overrides: [backupRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: BackupScreen()),
    );
  }

  testWidgets('renders export and import sections', (tester) async {
    await tester.pumpWidget(wrap(_FakeBackupRepository()));
    await tester.pumpAndSettle();

    expect(find.text('Backup & Restore'), findsOneWidget);
    expect(find.text('Export backup'), findsWidgets);
    expect(find.text('Import backup'), findsOneWidget);
    expect(find.text('Choose backup file'), findsOneWidget);
    expect(find.text('Restore pending'), findsNothing);
  });

  testWidgets('shows the pending-restore banner when a restore is staged',
      (tester) async {
    await tester.pumpWidget(wrap(_FakeBackupRepository(restorePending: true)));
    await tester.pumpAndSettle();

    expect(find.text('Restore pending'), findsOneWidget);
    expect(find.text('Cancel restore'), findsOneWidget);
  });

  testWidgets('cancelling a pending restore clears the banner', (tester) async {
    final repo = _FakeBackupRepository(restorePending: true);
    await tester.pumpWidget(wrap(repo));
    await tester.pumpAndSettle();

    expect(find.text('Restore pending'), findsOneWidget);

    await tester.tap(find.text('Cancel restore'));
    await tester.pumpAndSettle();

    expect(repo.cancelCallCount, 1);
    expect(find.text('Restore pending'), findsNothing);
    expect(find.text('Staged restore cancelled.'), findsOneWidget);
  });
}
