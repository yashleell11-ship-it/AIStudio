import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository_impl.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository_impl.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository_impl.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository_impl.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final libraryRepositoryProvider = Provider<LibraryRepository>(
  (ref) => LibraryRepositoryImpl(ref.watch(dioProvider)),
  name: 'libraryRepository',
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
