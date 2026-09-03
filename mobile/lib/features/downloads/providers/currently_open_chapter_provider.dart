import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';

/// The chapter identity currently open in either reader screen, plus which
/// scope opened it — set on mount, cleared on dispose (see
/// `widgets/open_chapter_scope.dart`). Consulted by the read-then-expire
/// sweep and cap eviction so neither can ever delete the chapter someone is
/// looking at right now, even if its timer already elapsed or storage
/// pressure is high.
final currentlyOpenChapterProvider =
    StateProvider<ScopedChapterIdentity?>((_) => null, name: 'currentlyOpenChapter');
