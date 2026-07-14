import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/widgets/whats_new_sheet.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Wraps the app and, once per launch, automatically opens the "What's new"
/// sheet if the running build is newer than the one the user last saw it
/// for. A brand-new install (nothing recorded yet) is never shown the sheet
/// — there's no "new" to compare against — it just starts recording from
/// here on.
class WhatsNewAutoShow extends ConsumerStatefulWidget {
  const WhatsNewAutoShow({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<WhatsNewAutoShow> createState() => _WhatsNewAutoShowState();
}

class _WhatsNewAutoShowState extends ConsumerState<WhatsNewAutoShow>
    with WidgetsBindingObserver {
  var _checked = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeShow());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    // When the user returns after installing a new APK, re-read the installed
    // package info and re-run the backend version check so the "installed"
    // build and the update banner reflect the freshly-installed version
    // without needing a manual restart. On Android a self-update kills the
    // process, so the next launch is already fresh; this covers the case where
    // the process survives (e.g. update applied while briefly backgrounded).
    ref.invalidate(packageInfoProvider);
    ref.invalidate(appUpdateProvider);
  }

  Future<void> _maybeShow() async {
    if (_checked || !mounted) return;
    _checked = true;

    final prefs = ref.read(preferencesProvider);
    final info = await ref.read(packageInfoProvider.future);
    final currentBuild = int.tryParse(info.buildNumber) ?? 0;
    if (currentBuild <= 0) return;

    final lastSeen = prefs.lastSeenChangelogBuild;
    final isUpdate =
        lastSeen > 0 && currentBuild > lastSeen && prefs.setupCompleted;
    await prefs.setLastSeenChangelogBuild(currentBuild);

    if (isUpdate && mounted) {
      await showWhatsNewSheet(context);
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
