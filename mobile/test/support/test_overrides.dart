import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Overrides [apiBaseUrlProvider] for widget/provider tests.
Override apiBaseUrlOverride(String url) =>
    apiBaseUrlProvider.overrideWith((ref) => StateController(url));

const setupCompletedPrefKey = 'settings_setup_completed';

/// Default prefs so tests skip the first-run setup redirect.
Map<String, Object> testPrefsDefaults([Map<String, Object> extra = const {}]) {
  return {
    setupCompletedPrefKey: true,
    ...extra,
  };
}
