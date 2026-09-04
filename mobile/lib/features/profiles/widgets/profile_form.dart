import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
    this.initialMatureContentEnabled = false,
    this.onDelete,
  });

  final String title;
  final String submitLabel;
  final Future<AppError?> Function(
    String name,
    String avatarKey,
    Mood mood,
    bool matureContentEnabled,
  ) onSubmit;
  final VoidCallback onSuccess;
  final String initialName;
  final String initialAvatarKey;
  final Mood initialMood;
  final bool initialMatureContentEnabled;

  /// When supplied, renders a destructive "Delete profile" action.
  final Future<AppError?> Function()? onDelete;

  @override
  State<ProfileFormScaffold> createState() => _ProfileFormScaffoldState();
}

class _ProfileFormScaffoldState extends State<ProfileFormScaffold> {
  late final TextEditingController _nameController;
  late String _avatarKey;
  late Mood _mood;
  late bool _matureContentEnabled;
  var _pending = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.initialName);
    _avatarKey = widget.initialAvatarKey;
    _mood = widget.initialMood;
    _matureContentEnabled = widget.initialMatureContentEnabled;
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
    final error = await widget.onSubmit(
      name,
      _avatarKey,
      _mood,
      _matureContentEnabled,
    );
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
            style: FilledButton.styleFrom(backgroundColor: context.colors.danger),
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
              context.space.xl2,
              context.space.lg,
              context.space.xl2,
              MediaQuery.paddingOf(context).bottom + context.space.xl3,
            ),
            children: [
              Center(
                child: ProfileAvatar(
                  avatarKey: _avatarKey,
                  ringColor: context.colors.accentAmber.withValues(alpha: 0.3),
                ),
              ),
              SizedBox(height: context.space.xl2),
              Text('Name', style: context.text.labelLg),
              SizedBox(height: context.space.sm),
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
              SizedBox(height: context.space.md),
              Text('Avatar', style: context.text.labelLg),
              SizedBox(height: context.space.sm),
              _AvatarPicker(
                selectedKey: _avatarKey,
                onSelected: _pending
                    ? null
                    : (key) => setState(() => _avatarKey = key),
              ),
              SizedBox(height: context.space.xl),
              Text('Mood', style: context.text.labelLg),
              SizedBox(height: context.space.xxs),
              Text(
                'Tints the app while this profile is active.',
                style: context.text.bodySm.copyWith(color: context.colors.muted),
              ),
              SizedBox(height: context.space.sm),
              _MoodPicker(
                selected: _mood,
                onSelected:
                    _pending ? null : (mood) => setState(() => _mood = mood),
              ),
              SizedBox(height: context.space.xl),
              Material(
                type: MaterialType.transparency,
                child: SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  activeThumbColor: context.colors.primary,
                  title: const Text('Mature content'),
                  subtitle: const Text(
                    'Show 18+ sources and series for this profile.',
                  ),
                  value: _matureContentEnabled,
                  onChanged: _pending
                      ? null
                      : (value) =>
                          setState(() => _matureContentEnabled = value),
                ),
              ),
              if (error != null) ...[
                SizedBox(height: context.space.lg),
                AuthError(message: error),
              ],
              SizedBox(height: context.space.xl),
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
                SizedBox(height: context.space.sm),
                TextButton.icon(
                  onPressed: _pending ? null : _delete,
                  icon: const Icon(Icons.delete_outline, size: 18),
                  label: const Text('Delete profile'),
                  style: TextButton.styleFrom(
                    foregroundColor: context.colors.danger,
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
      spacing: context.space.md,
      runSpacing: context.space.md,
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
                    preset.key == selectedKey ? context.colors.primary : null,
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
      spacing: context.space.sm,
      runSpacing: context.space.sm,
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
        ? Color.lerp(context.colors.bg, mood.tint, 0.6)!
        : context.colors.surface2;
    return Material(
      color: selected ? swatch.withAlpha(220) : context.colors.surface2.withAlpha(120),
      borderRadius: BorderRadius.circular(context.radii.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(context.radii.full),
        onTap: onTap,
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.md,
            vertical: context.space.sm,
          ),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(context.radii.full),
            border: Border.all(
              color: selected ? context.colors.fg.withAlpha(120) : context.colors.border,
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
                      ? Color.lerp(context.colors.bg, mood.tint, 0.7)!
                      : context.colors.muted,
                  border: Border.all(color: context.colors.fg.withAlpha(40)),
                ),
              ),
              SizedBox(width: context.space.sm),
              Text(
                mood.label,
                style: context.text.label.copyWith(
                  color: selected ? context.colors.fg : context.colors.muted,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
