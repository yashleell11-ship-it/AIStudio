import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/auth/widgets/auth_error.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile_avatar.dart';
import 'package:manhwamaniacs/features/profiles/widgets/mood_backdrop.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_avatar.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';

/// Shared create/edit form for a reading profile. The surrounding backdrop
/// previews the picked [Mood] live. Delegates persistence to [onSubmit] (and
/// optional [onDelete]); both return an [AppError] to render inline or null on
/// success, after which [onSuccess] is invoked to navigate away.
class ProfileFormScaffold extends StatefulWidget {
  const ProfileFormScaffold({
    super.key,
    required this.title,
    required this.submitLabel,
    required this.onSubmit,
    required this.onSuccess,
    this.initialName = '',
    this.initialAvatarKey = kDefaultAvatarKey,
    this.initialMood = Mood.neutral,
    this.onDelete,
  });

  final String title;
  final String submitLabel;
  final Future<AppError?> Function(String name, String avatarKey, Mood mood)
      onSubmit;
  final VoidCallback onSuccess;
  final String initialName;
  final String initialAvatarKey;
  final Mood initialMood;

  /// When supplied, renders a destructive "Delete profile" action.
  final Future<AppError?> Function()? onDelete;

  @override
  State<ProfileFormScaffold> createState() => _ProfileFormScaffoldState();
}

class _ProfileFormScaffoldState extends State<ProfileFormScaffold> {
  late final TextEditingController _nameController;
  late String _avatarKey;
  late Mood _mood;
  var _pending = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.initialName);
    _avatarKey = widget.initialAvatarKey;
    _mood = widget.initialMood;
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_pending) return;
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Give this profile a name.');
      return;
    }
    setState(() {
      _pending = true;
      _error = null;
    });
    final error = await widget.onSubmit(name, _avatarKey, _mood);
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _pending = false;
        _error = error.userMessage;
      });
      return;
    }
    widget.onSuccess();
  }

  Future<void> _delete() async {
    final onDelete = widget.onDelete;
    if (onDelete == null || _pending) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete profile?'),
        content: Text(
          'This removes "${_nameController.text.trim()}" and its reading '
          'preferences. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _pending = true;
      _error = null;
    });
    final error = await onDelete();
    if (!mounted) return;
    if (error != null) {
      setState(() {
        _pending = false;
        _error = error.userMessage;
      });
      return;
    }
    widget.onSuccess();
  }

  @override
  Widget build(BuildContext context) {
    final error = _error;
    return MoodBackdrop(
      mood: _mood,
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          title: Text(widget.title),
          backgroundColor: Colors.transparent,
        ),
        body: SafeArea(
          top: false,
          child: ListView(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              AppSpacing.lg,
              AppSpacing.xl2,
              MediaQuery.paddingOf(context).bottom + AppSpacing.xl3,
            ),
            children: [
              Center(
                child: ProfileAvatar(
                  avatarKey: _avatarKey,
                  ringColor: AppColors.accentAmber.withValues(alpha: 0.3),
                ),
              ),
              const SizedBox(height: AppSpacing.xl2),
              Text('Name', style: AppTypography.labelLg),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: _nameController,
                maxLength: 255,
                enabled: !_pending,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(
                  hintText: 'e.g. Weeknight reads',
                  prefixIcon: Icon(Icons.badge_outlined),
                ),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: AppSpacing.md),
              Text('Avatar', style: AppTypography.labelLg),
              const SizedBox(height: AppSpacing.sm),
              _AvatarPicker(
                selectedKey: _avatarKey,
                onSelected: _pending
                    ? null
                    : (key) => setState(() => _avatarKey = key),
              ),
              const SizedBox(height: AppSpacing.xl),
              Text('Mood', style: AppTypography.labelLg),
              const SizedBox(height: AppSpacing.xxs),
              Text(
                'Tints the app while this profile is active.',
                style: AppTypography.bodySm.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.sm),
              _MoodPicker(
                selected: _mood,
                onSelected:
                    _pending ? null : (mood) => setState(() => _mood = mood),
              ),
              if (error != null) ...[
                const SizedBox(height: AppSpacing.lg),
                AuthError(message: error),
              ],
              const SizedBox(height: AppSpacing.xl),
              _pending
                  ? const SizedBox(
                      height: 52,
                      child: Center(
                        child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                    )
                  : PrimaryPillButton(
                      label: widget.submitLabel,
                      onPressed: _submit,
                      expanded: true,
                    ),
              if (widget.onDelete != null) ...[
                const SizedBox(height: AppSpacing.sm),
                TextButton.icon(
                  onPressed: _pending ? null : _delete,
                  icon: const Icon(Icons.delete_outline, size: 18),
                  label: const Text('Delete profile'),
                  style: TextButton.styleFrom(
                    foregroundColor: AppColors.danger,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _AvatarPicker extends StatelessWidget {
  const _AvatarPicker({required this.selectedKey, required this.onSelected});

  final String selectedKey;
  final ValueChanged<String>? onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.md,
      children: [
        for (final preset in kAvatarPresets)
          Semantics(
            label: preset.label,
            selected: preset.key == selectedKey,
            button: true,
            child: GestureDetector(
              onTap: onSelected == null ? null : () => onSelected!(preset.key),
              child: ProfileAvatar(
                avatarKey: preset.key,
                size: 56,
                ringColor:
                    preset.key == selectedKey ? AppColors.primary : null,
              ),
            ),
          ),
      ],
    );
  }
}

class _MoodPicker extends StatelessWidget {
  const _MoodPicker({required this.selected, required this.onSelected});

  final Mood selected;
  final ValueChanged<Mood>? onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final mood in Mood.values)
          _MoodChip(
            mood: mood,
            selected: mood == selected,
            onTap: onSelected == null ? null : () => onSelected!(mood),
          ),
      ],
    );
  }
}

class _MoodChip extends StatelessWidget {
  const _MoodChip({
    required this.mood,
    required this.selected,
    required this.onTap,
  });

  final Mood mood;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final swatch = mood.isTinted
        ? Color.lerp(ProfileMoodColors.base, mood.tint, 0.6)!
        : AppColors.surface2;
    return Material(
      color: selected ? swatch.withAlpha(220) : AppColors.surface2.withAlpha(120),
      borderRadius: BorderRadius.circular(AppRadius.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.full),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.full),
            border: Border.all(
              color: selected ? AppColors.fg.withAlpha(120) : AppColors.border,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: mood.isTinted
                      ? Color.lerp(ProfileMoodColors.base, mood.tint, 0.7)!
                      : AppColors.muted,
                  border: Border.all(color: AppColors.fg.withAlpha(40)),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                mood.label,
                style: AppTypography.label.copyWith(
                  color: selected ? AppColors.fg : AppColors.muted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
