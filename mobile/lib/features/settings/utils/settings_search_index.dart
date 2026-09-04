import 'package:flutter/material.dart';

/// One searchable entry: a setting's label, which Settings tab it lives on
/// (0=General, 1=Server, 2=About, 3=Debug), and optional context to widen
/// what a search term can match against.
class SettingsSearchEntry {
  const SettingsSearchEntry({
    required this.label,
    required this.tabIndex,
    this.subtitle,
    this.androidOnly = false,
  });

  final String label;
  final int tabIndex;
  final String? subtitle;

  /// True for settings backed by an Android-only platform channel
  /// (`flutter_displaymode`, the volume-key `NativeBridge`). The General tab
  /// hides those controls elsewhere, so search must not offer to jump to a
  /// switch that isn't rendered.
  final bool androidOnly;
}

/// Every setting a user can jump to via search. Kept as a flat, hand-written
/// index rather than reflecting over the widget tree -- Settings is a small,
/// stable surface, so a static list is simpler and never drifts silently out
/// of sync with what's rendered (each entry is added alongside its setting).
const List<SettingsSearchEntry> settingsSearchIndex = [
  SettingsSearchEntry(label: 'Show mature content (18+)', tabIndex: 0, subtitle: 'Adult-only series, NSFW, content'),
  SettingsSearchEntry(label: 'Reading history', tabIndex: 0, subtitle: 'Recently read chapters'),
  SettingsSearchEntry(label: 'Theme', tabIndex: 0, subtitle: 'Eclipse, Gruvbox, Nord, Dracula, Catppuccin, base16 & more'),
  SettingsSearchEntry(label: 'Design', tabIndex: 0, subtitle: 'Signature, Matte, Compact, Editorial, Cinema — density, surfaces, layout'),
  SettingsSearchEntry(label: 'Language', tabIndex: 0, subtitle: 'App language'),
  SettingsSearchEntry(label: 'Haptic feedback', tabIndex: 0, subtitle: 'Feedback'),
  SettingsSearchEntry(label: 'Reading direction', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Fit mode', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Refresh rate', tabIndex: 0, subtitle: 'Default reader preferences, FPS', androidOnly: true),
  SettingsSearchEntry(label: 'Keep screen awake', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Auto next chapter', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Lock reader controls', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Volume key navigation', tabIndex: 0, subtitle: 'Page turn with volume buttons', androidOnly: true),
  SettingsSearchEntry(label: 'Server connection', tabIndex: 1, subtitle: 'Server URL'),
  SettingsSearchEntry(label: 'Version', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Build', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Open source licenses', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Diagnostics', tabIndex: 3, subtitle: 'Performance, FPS, device info'),
  SettingsSearchEntry(label: 'Reset reader settings', tabIndex: 3, subtitle: 'Debug'),
];

/// Matching entries for [query], restricted to what [platform] actually
/// renders. [platform] is required rather than defaulted: a wrong default here
/// silently surfaces settings that do not exist on the device.
List<SettingsSearchEntry> filterSettingsSearchIndex(
  String query, {
  required TargetPlatform platform,
}) {
  final available = settingsSearchIndex.where(
    (entry) => !entry.androidOnly || platform == TargetPlatform.android,
  );
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return available.toList();
  return available
      .where((entry) =>
          entry.label.toLowerCase().contains(q) ||
          (entry.subtitle?.toLowerCase().contains(q) ?? false),)
      .toList();
}

/// Built-in [SearchDelegate] over [settingsSearchIndex]. Selecting a result
/// invokes [onSelectTab] with that setting's tab index and closes the search.
class SettingsSearchDelegate extends SearchDelegate<void> {
  SettingsSearchDelegate({required this.onSelectTab})
      : super(searchFieldLabel: 'Search settings');

  final ValueChanged<int> onSelectTab;

  @override
  List<Widget> buildActions(BuildContext context) => [
        if (query.isNotEmpty)
          IconButton(
            icon: const Icon(Icons.clear),
            onPressed: () => query = '',
          ),
      ];

  @override
  Widget buildLeading(BuildContext context) => IconButton(
        icon: const Icon(Icons.arrow_back),
        onPressed: () => close(context, null),
      );

  @override
  Widget buildResults(BuildContext context) => _buildList(context);

  @override
  Widget buildSuggestions(BuildContext context) => _buildList(context);

  Widget _buildList(BuildContext context) {
    final results = filterSettingsSearchIndex(
      query,
      platform: Theme.of(context).platform,
    );
    if (results.isEmpty) {
      return const Center(child: Text('No matching settings'));
    }
    return ListView.builder(
      itemCount: results.length,
      itemBuilder: (context, index) {
        final entry = results[index];
        return ListTile(
          title: Text(entry.label),
          subtitle: entry.subtitle != null ? Text(entry.subtitle!) : null,
          onTap: () {
            onSelectTab(entry.tabIndex);
            close(context, null);
          },
        );
      },
    );
  }
}
