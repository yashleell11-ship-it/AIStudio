import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/settings/providers/backup_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:url_launcher/url_launcher.dart';

class BackupScreen extends ConsumerStatefulWidget {
  const BackupScreen({super.key});

  @override
  ConsumerState<BackupScreen> createState() => _BackupScreenState();
}

class _BackupScreenState extends ConsumerState<BackupScreen> {
  var _exporting = false;
  var _importing = false;

  Future<void> _exportBackup() async {
    setState(() => _exporting = true);
    try {
      final baseUrl = ref.read(apiBaseUrlProvider);
      final uri = Uri.tryParse('$baseUrl/backup/export');
      if (uri == null) return;
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        _showSnack('Could not start the download.');
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _pickAndImportBackup() async {
    final picked = await FilePicker.platform.pickFiles();
    final path = picked?.files.single.path;
    if (path == null || !mounted) return;

    final confirmed = await _confirmRestore(picked!.files.single.name);
    if (!confirmed || !mounted) return;

    setState(() => _importing = true);
    try {
      final repo = ref.read(backupRepositoryProvider);
      final result = await repo.importBackup(path);
      if (!mounted) return;
      result.fold(
        ok: (_) {
          ref.invalidate(backupStatusProvider);
          _showStagedDialog();
        },
        err: (error) => _showSnack(error.userMessage),
      );
    } finally {
      if (mounted) setState(() => _importing = false);
    }
  }

  Future<bool> _confirmRestore(String fileName) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Restore this backup?'),
        content: Text(
          '"$fileName" will replace your ENTIRE library, reading history, '
          'bookmarks and collections the next time the server restarts. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(dialogCtx, true),
            child: const Text('Restore'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _showStagedDialog() async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Restore staged'),
        content: const Text(
          'Your backup was validated and is ready. Restart your '
          'ManhwaManiacs server to finish restoring it.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }

  Future<void> _cancelPendingRestore() async {
    final repo = ref.read(backupRepositoryProvider);
    final result = await repo.cancelPendingRestore();
    if (!mounted) return;
    result.fold(
      ok: (_) {
        ref.invalidate(backupStatusProvider);
        _showSnack('Staged restore cancelled.');
      },
      err: (error) => _showSnack(error.userMessage),
    );
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(backupStatusProvider);
    final restorePending = statusAsync.valueOrNull?.restorePending ?? false;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(Routes.settings),
        ),
        title: const Text('Backup & Restore'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        children: [
          if (restorePending) ...[
            _PendingRestoreBanner(onCancel: _cancelPendingRestore),
            const SizedBox(height: AppSpacing.xl2),
          ],
          _SectionCard(
            icon: Icons.upload_outlined,
            iconColor: AppColors.accent,
            title: 'Export backup',
            description:
                'Download a complete snapshot of your library, reading '
                'progress, bookmarks and collections as a single file.',
            child: FilledButton.icon(
              onPressed: _exporting ? null : _exportBackup,
              icon: _exporting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.download_outlined, size: 18),
              label: Text(_exporting ? 'Starting download…' : 'Export backup'),
            ),
          ),
          const SizedBox(height: AppSpacing.xl2),
          _SectionCard(
            icon: Icons.download_outlined,
            iconColor: AppColors.warning,
            title: 'Import backup',
            description:
                'Restore from a previously exported backup file. This '
                'replaces all current data once the server restarts, so '
                'export a fresh backup first if you want to keep it.',
            child: OutlinedButton.icon(
              onPressed: _importing ? null : _pickAndImportBackup,
              icon: _importing
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.folder_open_outlined, size: 18),
              label: Text(_importing ? 'Uploading…' : 'Choose backup file'),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.description,
    required this.child,
  });

  final IconData icon;
  final Color iconColor;
  final String title;
  final String description;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: iconColor, size: 20),
              const SizedBox(width: AppSpacing.sm),
              Text(title, style: AppTypography.h4),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            description,
            style: AppTypography.bodySm.copyWith(color: AppColors.muted, height: 1.5),
          ),
          const SizedBox(height: AppSpacing.lg),
          child,
        ],
      ),
    );
  }
}

class _PendingRestoreBanner extends StatelessWidget {
  const _PendingRestoreBanner({required this.onCancel});

  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.warning.withAlpha(30), AppColors.warning.withAlpha(10)],
        ),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.warning.withAlpha(90)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.pending_actions_outlined, color: AppColors.warning, size: 18),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Restore pending',
                  style: AppTypography.labelLg.copyWith(color: AppColors.warning),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'A backup is staged and will be applied the next time your '
              'server restarts.',
              style: AppTypography.bodySm.copyWith(color: AppColors.muted),
            ),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              onPressed: onCancel,
              child: const Text('Cancel restore'),
            ),
          ],
        ),
      ),
    );
  }
}
