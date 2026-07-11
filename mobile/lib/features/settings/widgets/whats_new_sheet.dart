import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/settings/models/app_changelog.dart';
import 'package:manhwamaniacs/features/settings/providers/app_changelog_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';

/// Opens the "What's new" release-notes sheet, sourced live from the backend
/// changelog (the same notes rendered on the install landing page).
Future<void> showWhatsNewSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: AppColors.surface,
    constraints: const BoxConstraints(maxWidth: 640),
    builder: (_) => const WhatsNewSheet(),
  );
}

class WhatsNewSheet extends ConsumerWidget {
  const WhatsNewSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final releasesAsync = ref.watch(appChangelogProvider);

    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.8,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xl2,
                0,
                AppSpacing.xl2,
                AppSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("What's new", style: AppTypography.h2),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(
                    'Recent improvements to ManhwaManiacs',
                    style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
            Flexible(
              child: releasesAsync.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xl5),
                  child: Center(
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ),
                error: (_, __) => const _Unavailable(),
                data: (releases) {
                  if (releases.isEmpty) return const _Unavailable();
                  return ListView.separated(
                    shrinkWrap: true,
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.xl2,
                      0,
                      AppSpacing.xl2,
                      AppSpacing.xl2,
                    ),
                    itemCount: releases.length,
                    separatorBuilder: (_, __) =>
                        const SizedBox(height: AppSpacing.lg),
                    itemBuilder: (_, i) => _ReleaseCard(
                      release: releases[i],
                      isLatest: i == 0,
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.xl2),
      child: EmptyState(
        icon: Icons.cloud_off_outlined,
        message: 'Release notes unavailable',
        subtitle: "Connect to your server to see what's changed.",
      ),
    );
  }
}

class _ReleaseCard extends StatelessWidget {
  const _ReleaseCard({required this.release, required this.isLatest});

  final ChangelogRelease release;
  final bool isLatest;

  @override
  Widget build(BuildContext context) {
    final meta = <String>[
      if (release.date.isNotEmpty) release.date,
      if (release.build > 0) 'build ${release.build}',
    ].join(' · ');

    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xxs,
                ),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [AppColors.primary, AppColors.violet600],
                  ),
                  borderRadius: BorderRadius.circular(AppRadius.full),
                ),
                child: Text(
                  'v${release.version}',
                  style: AppTypography.labelSm.copyWith(
                    color: AppColors.primaryFg,
                  ),
                ),
              ),
              if (isLatest) ...[
                const SizedBox(width: AppSpacing.sm),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xxs,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.accent.withAlpha(30),
                    borderRadius: BorderRadius.circular(AppRadius.full),
                    border: Border.all(color: AppColors.accent.withAlpha(90)),
                  ),
                  child: Text(
                    'Latest',
                    style: AppTypography.labelSm.copyWith(
                      color: AppColors.cyan400,
                    ),
                  ),
                ),
              ],
              const Spacer(),
              if (meta.isNotEmpty)
                Flexible(
                  child: Text(
                    meta,
                    textAlign: TextAlign.right,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption,
                  ),
                ),
            ],
          ),
          if (release.highlights.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            for (final note in release.highlights)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      margin: const EdgeInsets.only(top: 7),
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        gradient: LinearGradient(
                          colors: [AppColors.primary, AppColors.accent],
                        ),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        note,
                        style: AppTypography.body.copyWith(
                          color: AppColors.fg.withAlpha(220),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}
