import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Whether any novel UI may exist right now — the single production gate.
///
/// `novels_enabled` rides on `GET /auth/bootstrap-status`, the pre-auth probe
/// the client already makes once per launch, so the app ships the novel code
/// dormant and one env var on the VPS turns it on. Every novel surface mounts
/// behind this: with the flag off the app must look **exactly** as it does
/// today.
///
/// Deliberately **not** `autoDispose`, unlike [bootstrapStatusProvider]: that
/// one is read by two screens that are mounted once each, while this is read
/// by nearly every list in the app. An auto-disposing gate would re-probe the
/// server on every tab switch, and — worse — flicker back through `null` while
/// it did, blanking a novel screen mid-scroll.
///
/// A failure resolves to **off**, never to an error: an unreachable server
/// must leave the owner in the app he uses daily rather than on an error
/// state, and "no answer" is the same practical situation as a deployment
/// that has no novel connectors. [novelsEnabledProvider] flattens both the
/// loading and the error case to `false` for exactly that reason.
final novelsGateProvider = FutureProvider<bool>(
  (ref) async {
    final result = await ref.read(authRepositoryProvider).bootstrapStatus();
    if (result.isErr) return false;
    return result.value.novelsEnabled;
  },
  name: 'novelsGate',
);

/// The gate as a plain bool: `false` while loading, `false` on failure.
///
/// Every caller wants this rather than the `AsyncValue` — "we don't know yet"
/// and "no" render identically (today's app), so branching on the three states
/// would only ever produce the same widget twice.
final novelsEnabledProvider = Provider<bool>(
  (ref) => ref.watch(novelsGateProvider).valueOrNull ?? false,
  name: 'novelsEnabled',
);
