import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Navigates to the library reader route for a downloaded chapter.
Future<void> openDownloadedChapter(
  BuildContext context,
  WidgetRef ref,
  DownloadItem item,
) async {
  final localChapterId = item.localChapterId;
  if (localChapterId == null) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('This download is not available offline yet.')),
    );
    return;
  }

  final result = await ref.read(libraryRepositoryProvider).getChapter(localChapterId);
  if (!context.mounted) return;
  if (result.isErr) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.error.userMessage)),
    );
    return;
  }

  context.go(RoutePaths.reader(result.value.seriesId, localChapterId));
}

String libraryReaderPath(
  int seriesId,
  int chapterId, {
  int initialPage = 1,
}) {
  final path = RoutePaths.reader(seriesId, chapterId);
  if (initialPage > 1) {
    return '$path?page=$initialPage';
  }
  return path;
}

/// Replaces the current route with the library reader once mounted.
///
/// Used when a source reader fetch resolves to [ReaderMode.local] so adjacent
/// navigation, progress, and bookmarks reuse [ReaderScreen].
class LocalReaderHandoff extends StatefulWidget {
  const LocalReaderHandoff({
    super.key,
    required this.seriesId,
    required this.chapterId,
    this.initialPage = 1,
  });

  final int seriesId;
  final int chapterId;
  final int initialPage;

  @override
  State<LocalReaderHandoff> createState() => _LocalReaderHandoffState();
}

class _LocalReaderHandoffState extends State<LocalReaderHandoff> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.go(
        libraryReaderPath(
          widget.seriesId,
          widget.chapterId,
          initialPage: widget.initialPage,
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) => const ReaderSkeleton();
}