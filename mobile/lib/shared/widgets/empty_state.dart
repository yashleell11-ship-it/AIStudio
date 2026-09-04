import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.subtitle,
    this.action,
  });

  final String message;
  final IconData icon;
  final String? subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(context.space.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Icon in a glowing circle
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: context.colors.muted.withAlpha(18),
                border: Border.all(color: context.colors.border.withAlpha(80)),
              ),
              child: Icon(icon, size: 36, color: context.colors.muted.withAlpha(160)),
            ),
            SizedBox(height: context.space.xl2),
            Text(
              message,
              style: context.text.h4,
              textAlign: TextAlign.center,
            ),
            if (subtitle != null) ...[
              SizedBox(height: context.space.sm),
              Text(
                subtitle!,
                style: context.text.body.copyWith(
                  color: context.colors.muted,
                  height: 1.6,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            if (action != null) ...[
              SizedBox(height: context.space.xl2),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}
