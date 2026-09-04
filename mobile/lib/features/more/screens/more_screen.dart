import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_sheet.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/widgets/premium/glass_panel.dart';
import 'package:url_launcher/url_launcher.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // On the SideStore channel there is no actionable banner to show — the
    // build numbers are not comparable and `/app/download` is an Android
    // package (see AppVersionInfo.hasUpdate) — so skip the check entirely
    // rather than firing a request whose answer can only be discarded.
    final updateAsync =
        AppUpdateChannel.forPlatform(Theme.of(context).platform) ==
                AppUpdateChannel.apk
            ? ref.watch(appUpdateProvider)
            : const AsyncValue<AppVersionInfo?>.data(null);
    final updatesAsync = ref.watch(updatesProvider);
    final unreadCount =
        updatesAsync.valueOrNull?.unreadCount ?? 0;
    // Spec §4: no platform OCR engine means no OCR surface at all. Dialogue
    // search is server-backed and would technically work without one, but a
    // device that can never contribute a transcript is also a device where
    // this entry would mostly lead to an empty screen — so it lives or dies
    // with the rest of the feature.
    final ocrVisible = ref.watch(ocrFeatureVisibleProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: EdgeInsets.only(
          left: AppSpacing.lg,
          right: AppSpacing.lg,
          top: AppSpacing.md,
          bottom: MediaQuery.paddingOf(context).bottom + AppSpacing.xl7,
        ),
        // Everything that leaves this tab uses `push`, never `go`.
        //
        // Updates / Collections / Settings / Storage / Backup are *top-level*
        // routes, siblings of the shell rather than children of it, so `go`
        // collapsed the stack to a single page. `Navigator.canPop()` was then
        // false and `CupertinoPageTransitionsBuilder` declines to install its
        // back-swipe on a route that cannot pop — leaving those five screens
        // with no edge-swipe at all on a phone with no hardware back button.
        // `push` keeps the More tab underneath, which also gives the gesture
        // something to parallax.
        //
        // The Library-section tiles below stay on `go` on purpose: their
        // targets live inside the Library shell branch, so `go` already
        // produces a poppable two-page stack there.
        children: [
          const _SectionHeader('Discover'),
          _MoreTile(
            icon: Icons.notifications_outlined,
            selectedIcon: Icons.notifications,
            label: 'Updates',
            badge: unreadCount > 0 ? '$unreadCount' : null,
            onTap: () => context.push(Routes.updates),
          ),
          _MoreTile(
            icon: Icons.collections_bookmark_outlined,
            selectedIcon: Icons.collections_bookmark,
            label: 'Collections',
            onTap: () => context.push(Routes.collections),
          ),
          const SizedBox(height: AppSpacing.md),
          const _SectionHeader('Account'),
          _MoreTile(
            icon: Icons.person_outline,
            selectedIcon: Icons.person,
            label: 'Switch profile',
            onTap: () => context.push(ProfileRoutes.picker),
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
            onTap: () => context.push(Routes.settings),
          ),
          // Downloads is a bottom-nav tab of its own now — a duplicate entry
          // here would push a second, chrome-less copy of the same screen
          // outside the shell.
          _MoreTile(
            icon: Icons.storage_outlined,
            selectedIcon: Icons.storage,
            label: 'Storage',
            onTap: () => context.push(Routes.storage),
          ),
          if (ocrVisible)
            _MoreTile(
              icon: Icons.text_fields_outlined,
              selectedIcon: Icons.text_fields,
              label: 'Dialogue Search',
              onTap: () => context.push(Routes.ocrSearch),
            ),
          _MoreTile(
            icon: Icons.backup_outlined,
            selectedIcon: Icons.backup,
            label: 'Backup & Restore',
            onTap: () => context.push(Routes.backup),
          ),
          updateAsync.when(
            skipLoadingOnReload: true,
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
            data: (info) {
              // Hide whenever the installed build is at or ahead of the remote
              // build (`hasUpdate == remoteBuild > localBuild`). After the user
              // installs the new APK and returns, the resume refresh re-reads
              // the now-current build and this collapses automatically.
              if (info == null || !info.hasUpdate) return const SizedBox.shrink();
              return _UpdateBanner(info: info);
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
          const _AppInfoTile(),
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
      leading: Icon(icon, color: AppColors.accentAmber, size: 22),
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
  const _UpdateBanner({required this.info});

  final AppVersionInfo info;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: GlassPanel(
        borderRadius: AppRadius.lg,
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: DecoratedBox(
          // Warm amber wash + glow layered inside the frosted panel.
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                AppColors.accentAmber.withAlpha(28),
                AppColors.accentRose.withAlpha(14),
              ],
            ),
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(
                      Icons.system_update_outlined,
                      color: AppColors.accentAmber,
                      size: 18,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Text(
                      'Update available',
                      style: AppTypography.labelLg.copyWith(
                        color: AppColors.accentAmber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                _VersionRow(
                  label: 'Installed',
                  version: info.localVersion,
                  buildNumber: info.localBuild,
                  emphasized: false,
                ),
                const SizedBox(height: AppSpacing.xxs),
                _VersionRow(
                  label: 'Available',
                  version: info.remoteVersion,
                  buildNumber: info.remoteBuild,
                  emphasized: true,
                ),
                const SizedBox(height: AppSpacing.md),
                FilledButton.icon(
                  onPressed: () => _launchDownload(context, info.downloadUrl),
                  icon: const Icon(Icons.download_outlined, size: 16),
                  label: const Text('Download update'),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Downloading does not install automatically. Open the '
                  'downloaded file to install, then return here.',
                  style: AppTypography.caption.copyWith(color: AppColors.muted),
                ),
                const SizedBox(height: AppSpacing.xxs),
                Text(
                  'Updating from 1.2.x? Uninstall the old app first.',
                  style: AppTypography.caption.copyWith(color: AppColors.muted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _launchDownload(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!context.mounted) return;
    if (!launched) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open: $url')),
      );
      return;
    }
    await _showInstallGuidance(context);
  }

  Future<void> _showInstallGuidance(BuildContext context) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: AppColors.surfaceElevated,
        title: Row(
          children: [
            const Icon(
              Icons.install_mobile_outlined,
              color: AppColors.accentAmber,
              size: 20,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text('Install now', style: AppTypography.h3),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'The new version is downloading to your device.',
              style: AppTypography.body.copyWith(color: AppColors.fg),
            ),
            const SizedBox(height: AppSpacing.md),
            const _Step(
              number: '1',
              text: 'Open the downloaded APK from your notification shade '
                  'or Downloads.',
            ),
            const _Step(
              number: '2',
              text: 'Tap Install and confirm any prompt.',
            ),
            const _Step(
              number: '3',
              text: 'Return here — the version updates and this banner '
                  'clears automatically.',
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}

class _VersionRow extends StatelessWidget {
  const _VersionRow({
    required this.label,
    required this.version,
    required this.buildNumber,
    required this.emphasized,
  });

  final String label;
  final String version;
  final int buildNumber;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(
          width: 72,
          child: Text(
            label,
            style: AppTypography.bodySm.copyWith(color: AppColors.muted),
          ),
        ),
        Text(
          'v$version',
          style: AppTypography.bodySm.copyWith(
            color: emphasized ? AppColors.accentAmber : AppColors.fg,
            fontWeight: emphasized ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          '(build $buildNumber)',
          style: AppTypography.caption.copyWith(color: AppColors.muted),
        ),
      ],
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({required this.number, required this.text});

  final String number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.accentAmber.withAlpha(36),
              shape: BoxShape.circle,
            ),
            child: Text(
              number,
              style: AppTypography.caption.copyWith(
                color: AppColors.accentAmber,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              text,
              style: AppTypography.bodySm.copyWith(color: AppColors.fg),
            ),
          ),
        ],
      ),
    );
  }
}

class _AppInfoTile extends ConsumerWidget {
  const _AppInfoTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final infoAsync = ref.watch(packageInfoProvider);

    return infoAsync.when(
      // Keep the tile visible while the provider re-reads on resume so the
      // version label swaps in place rather than blanking out.
      skipLoadingOnReload: true,
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
              colors: [AppColors.accentAmber, AppColors.accentRose],
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
        onTap: () => context.push(Routes.settings),
      ),
    );
  }
}
