import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/collections/utils/collection_sorting.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

class CollectionBannerCard extends StatelessWidget {
  const CollectionBannerCard({
    super.key,
    required this.collection,
    required this.onTap,
  });

  final Collection collection;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final coverUrl = collectionCoverUrl(collection.coverUrl);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.xl),
            border: Border.all(color: context.colors.border.withAlpha(80)),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.xl),
            child: AspectRatio(
              aspectRatio: 21 / 9,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (coverUrl != null)
                    Image.network(
                      coverUrl,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => _GradientFallback(collection: collection),
                    )
                  else
                    _GradientFallback(collection: collection),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          context.colors.bg.withAlpha(242),
                          context.colors.bg.withAlpha(179),
                          context.colors.bg.withAlpha(77),
                        ],
                      ),
                    ),
                  ),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          context.colors.bg.withAlpha(204),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(AppSpacing.xl),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Text(
                          collection.name,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: AppTypography.h3.copyWith(color: Colors.white),
                        ),
                        if (collection.description != null &&
                            collection.description!.isNotEmpty) ...[
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            collection.description!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: AppTypography.body.copyWith(
                              color: Colors.white.withAlpha(179),
                            ),
                          ),
                        ],
                        const SizedBox(height: AppSpacing.sm),
                        Row(
                          children: [
                            Icon(
                              Icons.menu_book_outlined,
                              size: 14,
                              color: Colors.white.withAlpha(153),
                            ),
                            const SizedBox(width: AppSpacing.xs),
                            Text(
                              '${collection.seriesCount} series',
                              style: AppTypography.caption.copyWith(
                                color: Colors.white.withAlpha(153),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _GradientFallback extends StatelessWidget {
  const _GradientFallback({required this.collection});

  final Collection collection;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                context.colors.primary.withAlpha(0x66),
                context.colors.panel,
                context.colors.accent.withAlpha(0x33),
              ],
            ),
          ),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(right: AppSpacing.xl3),
            child: Text(
              collectionInitials(collection.name),
              style: AppTypography.displayMd.copyWith(
                color: Colors.white.withAlpha(26),
                letterSpacing: 8,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class CollectionHeroBanner extends ConsumerWidget {
  const CollectionHeroBanner({
    super.key,
    required this.name,
    this.description,
    this.seriesCount = 0,
    this.coverUrl,
    this.coverSeriesRef,
    required this.apiBaseUrl,
  });

  final String name;
  final String? description;
  final int seriesCount;
  final String? coverUrl;

  /// `(sourceId, seriesKey)` of the first member series, used to resolve a
  /// cover through the source proxy when the collection has no cover of its
  /// own.
  final (String, String)? coverSeriesRef;
  final String apiBaseUrl;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ref_ = coverSeriesRef;
    final resolvedCover = coverUrl ??
        (ref_ != null ? sourceSeriesCoverUrl(apiBaseUrl, ref_.$1, ref_.$2) : null);

    return SizedBox(
      height: 220,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (resolvedCover != null)
            SeriesCoverImage(
              url: resolvedCover,
              borderRadius: 0,
            )
          else
            const _HeroGradient(),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  context.colors.bg.withAlpha(102),
                  context.colors.bg.withAlpha(204),
                  context.colors.bg,
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              AppSpacing.xl,
              AppSpacing.xl2,
              AppSpacing.xl2,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.displayMd,
                ),
                if (description != null && description!.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    description!,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.body.copyWith(color: context.colors.muted),
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                Row(
                  children: [
                    Icon(Icons.menu_book_outlined, size: 16, color: context.colors.accent),
                    const SizedBox(width: AppSpacing.xs),
                    Text(
                      '$seriesCount series',
                      style: AppTypography.body.copyWith(color: context.colors.muted),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroGradient extends StatelessWidget {
  const _HeroGradient();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            context.colors.primary.withAlpha(0x4D),
            context.colors.bg,
            context.colors.accent.withAlpha(0x33),
          ],
        ),
      ),
    );
  }
}

class CollectionFormDialog extends StatefulWidget {
  const CollectionFormDialog({
    super.key,
    required this.title,
    required this.submitLabel,
    this.initialName = '',
    this.initialDescription = '',
    required this.onSubmit,
  });

  final String title;
  final String submitLabel;
  final String initialName;
  final String initialDescription;
  final Future<AppError?> Function(String name, String? description) onSubmit;

  static Future<void> showCreate(
    BuildContext context, {
    required Future<AppError?> Function(String name, String? description) onCreate,
  }) {
    return showDialog<void>(
      context: context,
      builder: (context) => CollectionFormDialog(
        title: 'New Collection',
        submitLabel: 'Create',
        onSubmit: onCreate,
      ),
    );
  }

  static Future<void> showRename(
    BuildContext context, {
    required String initialName,
    String? initialDescription,
    required Future<AppError?> Function(String name, String? description) onRename,
  }) {
    return showDialog<void>(
      context: context,
      builder: (context) => CollectionFormDialog(
        title: 'Rename Collection',
        submitLabel: 'Save',
        initialName: initialName,
        initialDescription: initialDescription ?? '',
        onSubmit: onRename,
      ),
    );
  }

  @override
  State<CollectionFormDialog> createState() => _CollectionFormDialogState();
}

class _CollectionFormDialogState extends State<CollectionFormDialog> {
  late final TextEditingController _nameController;
  late final TextEditingController _descriptionController;
  var _submitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.initialName);
    _descriptionController = TextEditingController(text: widget.initialDescription);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty || _submitting) return;
    setState(() {
      _submitting = true;
      _errorMessage = null;
    });
    final error = await widget.onSubmit(
      name,
      _descriptionController.text.trim().isEmpty
          ? null
          : _descriptionController.text.trim(),
    );
    if (!mounted) return;
    if (error == null) {
      Navigator.of(context).pop();
      return;
    }
    setState(() {
      _submitting = false;
      _errorMessage = error.userMessage;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'Name',
                hintText: 'My Reading List',
              ),
              textInputAction: TextInputAction.next,
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              controller: _descriptionController,
              decoration: const InputDecoration(
                labelText: 'Description',
                hintText: 'Optional description',
              ),
              maxLines: 2,
            ),
            if (_errorMessage != null) ...[
              const SizedBox(height: AppSpacing.md),
              Text(
                _errorMessage!,
                style: AppTypography.caption.copyWith(color: context.colors.danger),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submitting || _nameController.text.trim().isEmpty ? null : _submit,
          child: Text(_submitting ? 'Saving…' : widget.submitLabel),
        ),
      ],
    );
  }
}
