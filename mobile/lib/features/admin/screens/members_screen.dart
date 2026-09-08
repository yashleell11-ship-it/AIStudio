import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/admin/members.dart';
import 'package:manhwamaniacs/features/admin/models/account.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Everyone who has signed up, and the two things an owner can do about it.
///
/// Registration on this server is open on purpose, which is exactly why this
/// screen exists: without it the owner can watch accounts appear and do
/// nothing. The website grew the same panel first; this is the phone catching
/// up, because the phone is where the owner actually is.
///
/// Pushed from the Settings account card rather than routed, like the security
/// screen: one entry point, nothing deep-links here.
class MembersScreen extends ConsumerStatefulWidget {
  const MembersScreen({super.key});

  @override
  ConsumerState<MembersScreen> createState() => _MembersScreenState();
}

class _MembersScreenState extends ConsumerState<MembersScreen> {
  late Future<void> _loaded;
  List<Account> _accounts = const [];
  String? _error;
  int? _busyId;

  @override
  void initState() {
    super.initState();
    _loaded = _load();
  }

  Future<void> _load() async {
    final result = await ref.read(adminRepositoryProvider).listAccounts();
    if (!mounted) return;
    setState(() {
      result.fold(
        ok: (rows) {
          _accounts = rows;
          _error = null;
        },
        err: (e) => _error = e.userMessage,
      );
    });
  }

  int? get _currentUserId {
    final state = ref.read(authControllerProvider);
    return state is AuthAuthenticated ? state.user.id : null;
  }

  Future<void> _setActive(Account account, bool active) async {
    setState(() => _busyId = account.id);
    final result = await ref
        .read(adminRepositoryProvider)
        .setActive(id: account.id, active: active);
    if (!mounted) return;
    setState(() {
      _busyId = null;
      result.fold(
        ok: (updated) {
          _accounts = [
            for (final row in _accounts)
              if (row.id == updated.id) updated else row,
          ];
        },
        err: (e) => _error = memberActionFailure(e.userMessage),
      );
    });
  }

  Future<void> _delete(Account account) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: Text('Delete @${account.username}?'),
        content: Text(deleteMemberPrompt(account)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogCtx).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: context.colors.danger,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busyId = account.id);
    final result = await ref
        .read(adminRepositoryProvider)
        .deleteAccount(account.id);
    if (!mounted) return;
    setState(() {
      _busyId = null;
      result.fold(
        ok: (_) => _accounts =
            _accounts.where((row) => row.id != account.id).toList(),
        err: (e) => _error = memberActionFailure(e.userMessage),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentUserId = _currentUserId;
    final rows = sortMembers(_accounts, currentUserId: currentUserId);

    return Scaffold(
      appBar: AppBar(title: const Text('Members')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: FutureBuilder<void>(
          future: _loaded,
          builder: (context, snapshot) {
            final loading =
                snapshot.connectionState == ConnectionState.waiting;
            return ListView(
              padding: EdgeInsets.all(context.space.xl2),
              children: [
                if (_error != null) ...[
                  AuthError(message: _error!),
                  SizedBox(height: context.space.lg),
                ],
                if (loading)
                  ...List.generate(
                    3,
                    (_) => Padding(
                      padding: EdgeInsets.only(bottom: context.space.md),
                      child: const SkeletonBox(width: null, height: 96),
                    ),
                  )
                else if (rows.isEmpty)
                  Text(
                    'No accounts yet.',
                    style: context.text.bodySm
                        .copyWith(color: context.colors.muted),
                  )
                else
                  for (final account in rows)
                    Padding(
                      padding: EdgeInsets.only(bottom: context.space.md),
                      child: _MemberCard(
                        account: account,
                        guard: memberRowGuard(
                          account,
                          currentUserId: currentUserId,
                        ),
                        busy: _busyId == account.id,
                        onToggleActive: () =>
                            _setActive(account, !account.isActive),
                        onDelete: () => _delete(account),
                      ),
                    ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _MemberCard extends StatelessWidget {
  const _MemberCard({
    required this.account,
    required this.guard,
    required this.busy,
    required this.onToggleActive,
    required this.onDelete,
  });

  final Account account;
  final MemberRowGuard guard;
  final bool busy;
  final VoidCallback onToggleActive;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '@${account.username}',
                  style: context.text.labelLg,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (account.isAdmin) const _Tag(label: 'Admin'),
              if (guard.isSelf) ...[
                SizedBox(width: context.space.xs),
                const _Tag(label: 'You'),
              ],
              if (!account.isActive) ...[
                SizedBox(width: context.space.xs),
                const _Tag(label: 'Deactivated', danger: true),
              ],
            ],
          ),
          SizedBox(height: context.space.xs),
          Text(
            _subtitle(account),
            style: context.text.bodySm.copyWith(color: context.colors.muted),
          ),
          SizedBox(height: context.space.md),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: guard.canManage && !busy ? onToggleActive : null,
                  child: Text(
                    account.isActive ? 'Deactivate' : 'Reactivate',
                  ),
                ),
              ),
              SizedBox(width: context.space.sm),
              Expanded(
                child: OutlinedButton(
                  onPressed: guard.canManage && !busy ? onDelete : null,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: context.colors.danger,
                  ),
                  child: const Text('Delete'),
                ),
              ),
            ],
          ),
          if (guard.reason != null) ...[
            SizedBox(height: context.space.xs),
            Text(
              guard.reason!,
              style: context.text.bodySm.copyWith(color: context.colors.muted),
            ),
          ],
        ],
      ),
    );
  }

  String _subtitle(Account account) {
    final joined = account.createdAt;
    final seen = account.lastLoginAt;
    final parts = <String>[
      if (joined != null) 'joined ${_day(joined.toLocal())}',
      seen != null ? 'last seen ${_day(seen.toLocal())}' : 'never signed in',
      '${account.sessionCount} '
          '${account.sessionCount == 1 ? 'session' : 'sessions'}',
    ];
    return parts.join(' · ');
  }

  String _day(DateTime value) =>
      '${value.year}-${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label, this.danger = false});

  final String label;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger ? context.colors.danger : context.colors.primary;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.space.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: context.text.bodySm.copyWith(color: color),
      ),
    );
  }
}
