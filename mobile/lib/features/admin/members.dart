import 'package:manhwamaniacs/features/admin/models/account.dart';

/// The reasons a row's controls are disabled, and the wording that explains it.
///
/// Kept out of the widget so the rules are testable without pumping a screen:
/// the one that matters is that an admin can never deactivate or delete
/// themselves. The server refuses it too, but a button that fails is worse
/// than a button that is visibly unavailable.
class MemberRowGuard {
  const MemberRowGuard({required this.isSelf});

  final bool isSelf;

  bool get canManage => !isSelf;

  /// Why the controls are off, for a tooltip. Null when they are on.
  String? get reason =>
      isSelf ? 'You cannot deactivate or delete your own account' : null;
}

MemberRowGuard memberRowGuard(Account account, {required int? currentUserId}) =>
    MemberRowGuard(isSelf: currentUserId != null && account.id == currentUserId);

/// Accounts in the order the list shows them: you first, then oldest signup
/// first.
///
/// Your own row leads because it is the one row you cannot act on, and finding
/// it immediately is what stops you hunting for the account you are about to
/// mistake for someone else's.
List<Account> sortMembers(List<Account> accounts, {required int? currentUserId}) {
  final sorted = [...accounts];
  sorted.sort((a, b) {
    final aSelf = currentUserId != null && a.id == currentUserId;
    final bSelf = currentUserId != null && b.id == currentUserId;
    if (aSelf != bSelf) return aSelf ? -1 : 1;
    final at = a.createdAt;
    final bt = b.createdAt;
    if (at != null && bt != null && at != bt) return at.compareTo(bt);
    return a.id.compareTo(b.id);
  });
  return sorted;
}

/// The confirmation shown before a delete, naming the account.
///
/// The username is in the body rather than only the title because on a phone
/// the title truncates, and a destructive confirmation that does not say who
/// it is about is not a confirmation.
String deleteMemberPrompt(Account account) =>
    'Delete @${account.username}? This removes their profiles, library, '
    'reading progress, bookmarks and everything else they own. '
    'It cannot be undone.';

/// What to say when a management call fails.
///
/// The server's own message is passed through when it has one — it is the only
/// thing that can explain a refusal this client did not anticipate, such as
/// the self-target 400.
String memberActionFailure(String? serverMessage) {
  final trimmed = serverMessage?.trim();
  if (trimmed == null || trimmed.isEmpty) return 'That did not work.';
  return trimmed;
}
