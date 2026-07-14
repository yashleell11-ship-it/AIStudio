import 'package:flutter/material.dart';

/// One searchable entry: a setting's label, which Settings tab it lives on
/// (0=General, 1=Server, 2=About, 3=Debug), and optional context to widen
/// what a search term can match against.
class SettingsSearchEntry {
  const SettingsSearchEntry({
    required this.label,
    required this.tabIndex,
    this.subtitle,
  });

  final String label;
  final int tabIndex;
  final String? subtitle;
}

/// Every setting a user can jump to via search. Kept as a flat, hand-written
/// index rather than reflecting over the widget tree -- Settings is a small,
/// stable surface, so a static list is simpler and never drifts silently out
/// of sync with what's rendered (each entry is added alongside its setting).
const List<SettingsSearchEntry> settingsSearchIndex = [
  SettingsSearchEntry(label: 'Show mature content (18+)', tabIndex: 0, subtitle: 'Adult-only series, NSFW, content'),
  SettingsSearchEntry(label: 'Reading history', tabIndex: 0, subtitle: 'Recently read chapters'),
  SettingsSearchEntry(label: 'Theme', tabIndex: 0, subtitle: 'Light, dark or system'),
  SettingsSearchEntry(label: 'Language', tabIndex: 0, subtitle: 'App language'),
  SettingsSearchEntry(label: 'Haptic feedback', tabIndex: 0, subtitle: 'Feedback'),
  SettingsSearchEntry(label: 'Reading direction', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Fit mode', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Refresh rate', tabIndex: 0, subtitle: 'Default reader preferences, FPS'),
  SettingsSearchEntry(label: 'Keep screen awake', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Auto next chapter', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Lock reader controls', tabIndex: 0, subtitle: 'Default reader preferences'),
  SettingsSearchEntry(label: 'Volume key navigation', tabIndex: 0, subtitle: 'Page turn with volume buttons'),
  SettingsSearchEntry(label: 'Concurrent chapters', tabIndex: 0, subtitle: 'Download preferences'),
  SettingsSearchEntry(label: 'Page concurrency', tabIndex: 0, subtitle: 'Download preferences'),
  SettingsSearchEntry(label: 'Retry count', tabIndex: 0, subtitle: 'Download preferences'),
  SettingsSearchEntry(label: 'Wi-Fi only', tabIndex: 0, subtitle: 'Download preferences, mobile data'),
  SettingsSearchEntry(label: 'Server connection', tabIndex: 1, subtitle: 'Server URL'),
  SettingsSearchEntry(label: 'Version', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Build', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Open source licenses', tabIndex: 2, subtitle: 'About'),
  SettingsSearchEntry(label: 'Diagnostics', tabIndex: 3, subtitle: 'Performance, FPS, device info'),
  SettingsSearchEntry(label: 'Reset reader settings', tabIndex: 3, subtitle: 'Debug'),
];

List<SettingsSearchEntry> filterSettingsSearchIndex(String query) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return settingsSearchIndex;
  return settingsSearchIndex
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
  Widget buildResults(BuildContext context) => _buildList();

  @override
  Widget buildSuggestions(BuildContext context) => _buildList();

  Widget _buildList() {
    final results = filterSettingsSearchIndex(query);
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
