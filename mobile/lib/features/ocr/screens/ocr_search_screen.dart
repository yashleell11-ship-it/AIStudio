import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_search_result.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_snippet.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// Full-text search over chapter dialogue (`GET /ocr/search`).
///
/// Results are scoped server-side to the series this profile follows and its
/// 18+ gate, so nothing here needs to filter — but it does mean an empty
/// result set for a term the user knows exists is usually "you don't follow
/// that series", which the empty state says out loud.
class OcrSearchScreen extends ConsumerStatefulWidget {
  const OcrSearchScreen({super.key});

  @override
  ConsumerState<OcrSearchScreen> createState() => _OcrSearchScreenState();
}

class _OcrSearchScreenState extends ConsumerState<OcrSearchScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;
  var _query = '';

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  /// Debounced so `ocrSearchProvider`'s family gains one key per settled
  /// query rather than one per keystroke — an FTS scan plus a followed-series
  /// filter is not a per-character cost worth paying.
  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (mounted) setState(() => _query = value);
    });
  }

  @override
  Widget build(BuildContext context) {
    final resultsAsync = ref.watch(ocrSearchProvider(_query));

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () => context.pop(),
        ),
        title: const Text('Dialogue search'),
      ),
      body: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.xl2,
              context.space.lg,
              context.space.xl2,
              context.space.md,
            ),
            child: TextField(
              key: const Key('ocr-search-field'),
              controller: _controller,
              autofocus: true,
              textInputAction: TextInputAction.search,
              onChanged: _onChanged,
              onSubmitted: (value) {
                _debounce?.cancel();
                setState(() => _query = value);
              },
              decoration: InputDecoration(
                hintText: 'Search text inside chapters',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(context.radii.lg),
                ),
              ),
            ),
          ),
          Expanded(
            child: _query.trim().isEmpty
                ? const EmptyState(
                    icon: Icons.text_fields,
                    message: 'Search chapter dialogue',
                    subtitle:
                        'Finds words inside chapters whose text has been '
                        'extracted, across the series you follow.',
                  )
                : resultsAsync.when(
                    loading: () =>
                        const Center(child: CircularProgressIndicator()),
                    error: (error, _) => Center(
                      child: Padding(
                        padding: EdgeInsets.all(context.space.xl2),
                        child: Text(
                          'Search failed — check your connection and try again.',
                          style: context.text.body
                              .copyWith(color: context.colors.danger),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                    data: (page) {
                      if (page.items.isEmpty) {
                        return const EmptyState(
                          icon: Icons.search_off,
                          message: 'No matches',
                          subtitle:
                              'Only chapters you have extracted text from, in '
                              'series you follow, can be searched.',
                        );
                      }
                      return ListView.builder(
                        padding: EdgeInsets.fromLTRB(
                          context.space.xl2,
                          0,
                          context.space.xl2,
                          context.space.xl2 + MediaQuery.paddingOf(context).bottom,
                        ),
                        itemCount: page.items.length,
                        itemBuilder: (context, index) => Padding(
                          padding: EdgeInsets.only(bottom: context.space.md),
                          child: _OcrResultCard(result: page.items[index]),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _OcrResultCard extends StatelessWidget {
  const _OcrResultCard({required this.result});

  final OcrSearchResult result;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: EdgeInsets.all(context.space.md),
      onTap: () => context.push(
        RoutePaths.reader(result.sourceId, result.seriesKey, result.chapterKey),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            result.seriesKey,
            style: context.text.labelLg,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          SizedBox(height: context.space.xxs),
          Text(
            '${result.sourceId} · ${result.chapterKey}',
            style: context.text.caption.copyWith(color: context.colors.muted),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          if (result.snippet.isNotEmpty) ...[
            SizedBox(height: context.space.sm),
            _Snippet(snippet: result.snippet),
          ],
        ],
      ),
    );
  }
}

/// Renders the backend's `<mark>`-tagged snippet as styled spans — see
/// `ocrSnippetSpans` for why the tags cannot simply be printed.
class _Snippet extends StatelessWidget {
  const _Snippet({required this.snippet});

  final String snippet;

  @override
  Widget build(BuildContext context) {
    final base = context.text.bodySm.copyWith(color: context.colors.muted);
    return Text.rich(
      TextSpan(
        children: [
          for (final span in ocrSnippetSpans(snippet))
            TextSpan(
              text: span.text,
              style: span.highlighted
                  ? base.copyWith(
                      color: context.colors.primary,
                      fontWeight: FontWeight.w600,
                    )
                  : base,
            ),
        ],
      ),
      maxLines: 4,
      overflow: TextOverflow.ellipsis,
    );
  }
}
