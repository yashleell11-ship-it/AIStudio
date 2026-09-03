import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository.dart';
import 'package:manhwamaniacs/features/auth/repositories/auth_repository_impl.dart';
import 'package:manhwamaniacs/features/library/repositories/global_search_repository.dart';
import 'package:manhwamaniacs/features/library/repositories/global_search_repository_impl.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository_impl.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository_impl.dart';
import 'package:manhwamaniacs/features/settings/repositories/backup_repository.dart';
import 'package:manhwamaniacs/features/settings/repositories/backup_repository_impl.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository_impl.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository_impl.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepositoryImpl(ref.watch(dioProvider)),
  name: 'authRepository',
);

final libraryRepositoryProvider = Provider<LibraryRepository>(
  (ref) => LibraryRepositoryImpl(ref.watch(dioProvider)),
  name: 'libraryRepository',
);

final globalSearchRepositoryProvider = Provider<GlobalSearchRepository>(
  (ref) => GlobalSearchRepositoryImpl(ref.watch(dioProvider)),
  name: 'globalSearchRepository',
);

final backupRepositoryProvider = Provider<BackupRepository>(
  (ref) => BackupRepositoryImpl(ref.watch(dioProvider)),
  name: 'backupRepository',
);

final readerRepositoryProvider = Provider<ReaderRepository>(
  (ref) => ReaderRepositoryImpl(ref.watch(dioProvider)),
  name: 'readerRepository',
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