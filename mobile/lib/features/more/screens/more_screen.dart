import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_sheet.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:url_launcher/url_launcher.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final updateAsync = ref.watch(appUpdateProvider);
    final updatesAsync = ref.watch(updatesProvider);
    final unreadCount =
        updatesAsync.valueOrNull?.unreadCount ?? 0;

    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: EdgeInsets.only(
          left: AppSpacing.lg,
          right: AppSpacing.lg,
          top: AppSpacing.md,
          bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.xl7,
        ),
        children: [
          const _SectionHeader('Discover'),
          _MoreTile(
            icon: Icons.notifications_outlined,
            selectedIcon: Icons.notifications,
            label: 'Updates',
            badge: unreadCount > 0 ? '$unreadCount' : null,
            onTap: () => context.go(Routes.updates),
          ),
          _MoreTile(
            icon: Icons.collections_bookmark_outlined,
            selectedIcon: Icons.collections_bookmark,
            label: 'Collections',
            onTap: () => context.go(Routes.collections),
          ),
          const SizedBox(height: AppSpacing.md),
          const _SectionHeader('Library'),
          _MoreTile(
            icon: Icons.history_outlined,
            selectedIcon: Icons.history,
            label: 'Reading History',
            onTap: () => context.go(Routes.readingHistory),
          ),
          _MoreTile(
            icon: Icons.bookmark_outline,
            selectedIcon: Icons.bookmark,
            label: 'Bookmarks',
            onTap: () => context.go(Routes.bookmarks),
          ),
          _MoreTile(
            icon: Icons.bar_chart_outlined,
            selectedIcon: Icons.bar_chart,
            label: 'Statistics',
            onTap: () => context.go(Routes.statistics),
          ),
          _MoreTile(
            icon: Icons.auto_awesome_outlined,
            selectedIcon: Icons.auto_awesome,
            label: 'Recommendations',
            onTap: () => context.go(Routes.recommendations),
          ),
          const SizedBox(height: AppSpacing.md),
          const _SectionHeader('App'),
          _MoreTile(
            icon: Icons.settings_outlined,
            selectedIcon: Icons.settings,
            label: 'Settings',
            onTap: () => context.go(Routes.settings),
          ),
          _MoreTile(
            icon: Icons.storage_outlined,
            selectedIcon: Icons.storage,
            label: 'Storage',
            onTap: () => context.go(Routes.storage),
          ),
          _MoreTile(
            icon: Icons.backup_outlined,
            selectedIcon: Icons.backup,
            label: 'Backup & Restore',
            onTap: () => context.go(Routes.backup),
          ),
          updateAsync.when(
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
            data: (info) {
              if (info == null || !info.hasUpdate) return const SizedBox.shrink();
              return _UpdateBanner(
                localVersion: info.localVersion,
                remoteVersion: info.remoteVersion,
                downloadUrl: info.downloadUrl,
              );
            },
          ),
          const SizedBox(height: AppSpacing.md),
          const _SectionHeader('About'),
          _MoreTile(
            icon: Icons.new_releases_outlined,
            selectedIcon: Icons.new_releases,
            label: "What's New",
            onTap: () => showWhatsNewSheet(context),
          ),
          _AppInfoTile(ref: ref),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(
        left: AppSpacing.sm,
        bottom: AppSpacing.xs,
        top: AppSpacing.xs,
      ),
      child: Text(
        title.toUpperCase(),
        style: AppTypography.labelSm.copyWith(
          color: AppColors.muted,
          letterSpacing: 1.0,
        ),
      ),
    );
  }
}

class _MoreTile extends StatelessWidget {
  const _MoreTile({
    required this.icon,
    required this.selectedIcon,
    required this.label,
    required this.onTap,
    this.badge,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
  final VoidCallback onTap;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xxs,
      ),
      leading: Icon(icon, color: AppColors.violet400, size: 22),
      title: Text(label, style: AppTypography.labelLg),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (badge != null)
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xxs,
              ),
              decoration: BoxDecoration(
                color: AppColors.primary,
                borderRadius: BorderRadius.circular(AppRadius.full),
              ),
              child: Text(
                badge!,
                style: AppTypography.labelSm.copyWith(
                  color: AppColors.primaryFg,
                ),
              ),
            ),
          const SizedBox(width: AppSpacing.xs),
          const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
        ],
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      onTap: onTap,
    );
  }
}

class _UpdateBanner extends StatelessWidget {
  const _UpdateBanner({
    required this.localVersion,
    required this.remoteVersion,
    required this.downloadUrl,
  });

  final String localVersion;
  final String remoteVersion;
  final String downloadUrl;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              AppColors.primary.withAlpha(30),
              AppColors.accent.withAlpha(15),
            ],
          ),
          borderRadius: BorderRadius.circular(AppRadius.lg),
          border: Border.all(color: AppColors.primary.withAlpha(80)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.system_update_outlined,
                    color: AppColors.violet400,
                    size: 18,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    'Update Available',
                    style: AppTypography.labelLg.copyWith(
                      color: AppColors.violet400,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                '$localVersion → $remoteVersion',
                style: AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.md),
              FilledButton.icon(
                onPressed: () => _launchDownload(context, downloadUrl),
                icon: const Icon(Icons.download_outlined, size: 16),
                label: const Text('Download Update'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _launchDownload(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!launched && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open: $url')),
      );
    }
  }
}

class _AppInfoTile extends ConsumerWidget {
  const _AppInfoTile({required this.ref});

  final WidgetRef ref;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final infoAsync = ref.watch(packageInfoProvider);

    return infoAsync.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (info) => ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [AppColors.primary, AppColors.violet600],
            ),
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          child: const Center(
            child: Text(
              'M',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 20,
              ),
            ),
          ),
        ),
        title: Text('ManhwaManiacs', style: AppTypography.labelLg),
        subtitle: Text(
          'v${info.version} (${info.buildNumber})',
          style: AppTypography.bodySm.copyWith(color: AppColors.muted),
        ),
        trailing: const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
        onTap: () => context.go(Routes.settings),
      ),
    );
  }
}
