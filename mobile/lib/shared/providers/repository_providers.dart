import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository_impl.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository_impl.dart';
import 'package:manhwamaniacs/features/settings/repositories/backup_repository.dart';
import 'package:manhwamaniacs/features/settings/repositories/backup_repository_impl.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository_impl.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository_impl.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

final libraryRepositoryProvider = Provider<LibraryRepository>(
  (ref) => LibraryRepositoryImpl(ref.watch(dioProvider)),
  name: 'libraryRepository',
);

final backupRepositoryProvider = Provider<BackupRepository>(
  (ref) => BackupRepositoryImpl(ref.watch(dioProvider)),
  name: 'backupRepository',
);

final downloadsRepositoryProvider = Provider<DownloadsRepository>(
  (ref) => DownloadsRepositoryImpl(ref.watch(dioProvider)),
  name: 'downloadsRepository',
);

final sourcesRepositoryProvider = Provider<SourcesRepository>(
  (ref) => SourcesRepositoryImpl(
    ref.watch(dioProvider),
    ref.watch(apiBaseUrlProvider),
  ),
  name: 'sourcesRepository',
);

final updatesRepositoryProvider = Provider<UpdatesRepository>(
  (ref) => UpdatesRepositoryImpl(ref.watch(dioProvider)),
  name: 'updatesRepository',
);