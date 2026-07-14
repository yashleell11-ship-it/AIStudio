import 'package:flutter/material.dart';
import 'package:manhwamaniacs/features/profiles/models/profile_avatar.dart';

/// A circular, gradient-filled avatar tile with the preset's glyph — the
/// Netflix-style face of a reading profile. Purely presentational.
class ProfileAvatar extends StatelessWidget {
  const ProfileAvatar({
    super.key,
    required this.avatarKey,
    this.size = 96,
    this.ringColor,
  });

  final String? avatarKey;
  final double size;

  /// When non-null, draws a focus ring around the tile (selected state).
  final Color? ringColor;

  @override
  Widget build(BuildContext context) {
    final preset = resolveAvatar(avatarKey);
    final ring = ringColor;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: preset.gradient,
        ),
        border: ring != null
            ? Border.all(color: ring, width: (size * 0.035).clamp(2.0, 4.0))
            : null,
        boxShadow: [
          BoxShadow(
            color: preset.gradient.last.withAlpha(70),
            blurRadius: size * 0.16,
            spreadRadius: -size * 0.04,
            offset: Offset(0, size * 0.05),
          ),
        ],
      ),
      alignment: Alignment.center,
      child: Icon(
        preset.icon,
        size: size * 0.42,
        color: Colors.white,
      ),
    );
  }
}
