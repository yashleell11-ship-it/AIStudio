import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';

/// Every chapter currently on screen in a reader, plus which scope opened it
/// — republished whenever the reader's feed changes and emptied when the
/// reader leaves (see `widgets/open_chapter_scope.dart`). Consulted by the
/// read-then-expire sweep and cap eviction so neither can ever delete a
/// chapter someone is looking at right now, even if its timer already
/// elapsed or storage pressure is high.
///
/// A SET, not a single identity: the continuous reader holds a window of up
/// to three chapters (spec R1/R2), and in a Read-all run that window SLIDES
/// — the chapter the route opened at is released from the feed long before
/// the three actually being read are. Claiming only the route chapter left
/// every neighbour on screen unprotected, and a neighbour finished on an
/// earlier read is exactly the row whose 48h timer has already elapsed.
final currentlyOpenChaptersProvider = StateProvider<Set<ScopedChapterIdentity>>(
  (_) => const {},
  name: 'currentlyOpenChapters',
);
