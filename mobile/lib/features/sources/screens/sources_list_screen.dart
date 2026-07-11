import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/source_branding.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class SourcesListScreen extends ConsumerWidget {
  const SourcesListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sourcesAsync = ref.watch(sourcesListProvider);
    final pinnedIds = ref.watch(pinnedSourcesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sources')),
      body: sourcesAsync.when(
        loading: () => ListView(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
          children: List.generate(
            8,
            (_) => const Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.sm,
              ),
              child: SkeletonBox(width: double.infinity, height: 60),
            ),
          ),
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError
                    ? error.userMessage
                    : 'Failed to load sources.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(sourcesListProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (sources) {
          if (sources.isEmpty) {
            return const EmptyState(
              icon: Icons.public_off,
              message: 'No sources installed',
              subtitle:
                  'Source connectors appear here when registered with the backend.',
            );
          }

          final byId = {for (final s in sources) s.id: s};
          final pinned = pinnedIds
              .map((id) => byId[id])
              .whereType<SourceSummary>()
              .toList();
          final browsable = sources
              .where((s) => s.browsable && !pinnedIds.contains(s.id))
              .toList();
          final bundled = sources
              .where((s) => !s.browsable && !pinnedIds.contains(s.id))
              .toList();

          void onTap(SourceSummary s) =>
              context.go(RoutePaths.sourceBrowse(s.id));

          void onLongPress(SourceSummary s) {
            ref.read(pinnedSourcesProvider.notifier).toggle(s.id);
            final isPinned = pinnedIds.contains(s.id);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  isPinned ? '${s.name} unpinned' : '${s.name} pinned',
                ),
                duration: const Duration(seconds: 2),
              ),
            );
          }

          const divider = Divider(
            height: 1,
            indent: 72,
            color: AppColors.border,
          );

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () async => ref.invalidate(sourcesListProvider),
            child: CustomScrollView(
              slivers: [
                if (pinned.isNotEmpty) ...[
                  const SliverPadding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      AppSpacing.lg,
                      AppSpacing.lg,
                      AppSpacing.xs,
                    ),
                    sliver: SliverToBoxAdapter(
                      child: _SectionLabel('Pinned'),
                    ),
                  ),
                  SliverList.separated(
                    itemCount: pinned.length,
                    separatorBuilder: (_, __) => divider,
                    itemBuilder: (context, index) => _SourceRow(
                      source: pinned[index],
                      isPinned: true,
                      onTap: () => onTap(pinned[index]),
                      onLongPress: () => onLongPress(pinned[index]),
                    ),
                  ),
                ],
                if (browsable.isNotEmpty) ...[
                  SliverPadding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      pinned.isEmpty ? AppSpacing.lg : AppSpacing.xl2,
                      AppSpacing.lg,
                      AppSpacing.xs,
                    ),
                    sliver: const SliverToBoxAdapter(
                      child: _SectionLabel('Online Sources'),
                    ),
                  ),
                  SliverList.separated(
                    itemCount: browsable.length,
                    separatorBuilder: (_, __) => divider,
                    itemBuilder: (context, index) => _SourceRow(
                      source: browsable[index],
                      onTap: () => onTap(browsable[index]),
                      onLongPress: () => onLongPress(browsable[index]),
                    ),
                  ),
                ],
                if (bundled.isNotEmpty) ...[
                  SliverPadding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      (pinned.isEmpty && browsable.isEmpty)
                          ? AppSpacing.lg
                          : AppSpacing.xl2,
                      AppSpacing.lg,
                      AppSpacing.xs,
                    ),
                    sliver: const SliverToBoxAdapter(
                      child: _SectionLabel('Bundled Sources'),
                    ),
                  ),
                  SliverList.separated(
                    itemCount: bundled.length,
                    separatorBuilder: (_, __) => divider,
                    itemBuilder: (context, index) => _SourceRow(
                      source: bundled[index],
                      onTap: () => onTap(bundled[index]),
                      onLongPress: () => onLongPress(bundled[index]),
                    ),
                  ),
                ],
                const SliverPadding(
                  padding: EdgeInsets.only(bottom: AppSpacing.xl7),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: AppTypography.labelSm.copyWith(
        color: AppColors.muted,
        letterSpacing: 0.8,
      ),
    );
  }
}

/// Dense source row: logo/avatar, name, description, capability badges, chevron.
class _SourceRow extends StatelessWidget {
  const _SourceRow({
    required this.source,
    required this.onTap,
    required this.onLongPress,
    this.isPinned = false,
  });

  final SourceSummary source;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final bool isPinned;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      onLongPress: onLongPress,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
        child: Row(
          children: [
            SourceLogo(id: source.id, name: source.name),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    source.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(
                    source.description,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.bodySm
                        .copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            if (source.supportsImport)
              const _MiniBadge(label: 'Import', color: AppColors.violet400),
            if (!source.browsable) ...[
              if (source.supportsImport) const SizedBox(width: AppSpacing.xs),
              const _MiniBadge(label: 'Bundled', color: AppColors.muted),
            ],
            if (isPinned) ...[
              const SizedBox(width: AppSpacing.xs),
              const Icon(Icons.push_pin, size: 14, color: AppColors.violet400),
            ],
            const SizedBox(width: AppSpacing.xs),
            const Icon(Icons.chevron_right, size: 18, color: AppColors.muted),
          ],
        ),
      ),
    );
  }
}

class _MiniBadge extends StatelessWidget {
  const _MiniBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xxs,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(28),
        borderRadius: BorderRadius.circular(AppRadius.full),
      ),
      child: Text(
        label,
        style: AppTypography.labelSm.copyWith(color: color),
      ),
    );
  }
}
