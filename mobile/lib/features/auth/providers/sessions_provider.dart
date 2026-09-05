import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/auth/models/user_session.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Every live server-side session for the signed-in account.
///
/// `autoDispose`, deliberately: this is a security audit the user opened a
/// screen to read, and a cached copy would answer "who is signed in?" with
/// what was true the last time they looked. Leaving the screen drops it; the
/// next visit asks the server again. Callers refresh after a revoke with
/// `ref.invalidate`.
///
/// Throws the [AppError] rather than folding it into the value so the screen
/// can use `AsyncValue.when` like every other network-backed surface.
final authSessionsProvider =
    FutureProvider.autoDispose<List<UserSession>>((ref) async {
  final result = await ref.read(authRepositoryProvider).sessions();
  if (result.isErr) throw result.error;
  return result.value;
});
