import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Overrides [apiBaseUrlProvider] for widget/provider tests.
Override apiBaseUrlOverride(String url) =>
    apiBaseUrlProvider.overrideWith((ref) => url);

const setupCompletedPrefKey = 'settings_setup_completed';

/// Default prefs so tests skip the first-run setup redirect.
Map<String, Object> testPrefsDefaults([Map<String, Object> extra = const {}]) {
  return {
    setupCompletedPrefKey: true,
    ...extra,
  };
}
