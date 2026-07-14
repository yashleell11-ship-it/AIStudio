import 'package:flutter/material.dart';

/// The fixed catalogue of profile avatars (mirrors
/// `frontend/src/features/profiles/avatars.ts`). A profile's `avatar_key`
/// references one of these by [key]; each pairs a glyph with a two-stop gradient
/// so avatars read as distinct coloured tiles (Netflix-style) rather than plain
/// initials. Keys match the web catalogue exactly so a profile created on either
/// client renders the same avatar everywhere.
///
/// This is the one place avatar presets live — adding an avatar means adding an
/// entry here.
@immutable
class AvatarPreset {
  const AvatarPreset({
    required this.key,
    required this.label,
    required this.icon,
    required this.gradient,
  });

  final String key;
  final String label;
  final IconData icon;

  /// Top-left → bottom-right gradient stops for the circular tile.
  final List<Color> gradient;
}

const List<AvatarPreset> kAvatarPresets = [
  AvatarPreset(
    key: 'violet',
    label: 'Violet Spark',
    icon: Icons.auto_awesome,
    gradient: [Color(0xFF8B5CF6), Color(0xFFD946EF)],
  ),
  AvatarPreset(
    key: 'cyan',
    label: 'Cyan Rocket',
    icon: Icons.rocket_launch,
    gradient: [Color(0xFF06B6D4), Color(0xFF0EA5E9)],
  ),
  AvatarPreset(
    key: 'rose',
    label: 'Rose Heart',
    icon: Icons.favorite,
    gradient: [Color(0xFFF43F5E), Color(0xFFEC4899)],
  ),
  AvatarPreset(
    key: 'amber',
    label: 'Amber Coffee',
    icon: Icons.local_cafe,
    gradient: [Color(0xFFF59E0B), Color(0xFFF97316)],
  ),
  AvatarPreset(
    key: 'emerald',
    label: 'Emerald Cat',
    icon: Icons.pets,
    gradient: [Color(0xFF10B981), Color(0xFF14B8A6)],
  ),
  AvatarPreset(
    key: 'ember',
    label: 'Ember Flame',
    icon: Icons.local_fire_department,
    gradient: [Color(0xFFEF4444), Color(0xFFF59E0B)],
  ),
  AvatarPreset(
    key: 'blade',
    label: 'Steel Blade',
    icon: Icons.shield,
    gradient: [Color(0xFF94A3B8), Color(0xFF475569)],
  ),
  AvatarPreset(
    key: 'phantom',
    label: 'Phantom',
    icon: Icons.blur_on,
    gradient: [Color(0xFF6366F1), Color(0xFF334155)],
  ),
  AvatarPreset(
    key: 'arcane',
    label: 'Arcane Wand',
    icon: Icons.auto_fix_high,
    gradient: [Color(0xFFA855F7), Color(0xFF6366F1)],
  ),
  AvatarPreset(
    key: 'lunar',
    label: 'Lunar Moon',
    icon: Icons.dark_mode,
    gradient: [Color(0xFF0284C7), Color(0xFF4338CA)],
  ),
  AvatarPreset(
    key: 'star',
    label: 'Starlight',
    icon: Icons.star,
    gradient: [Color(0xFFFACC15), Color(0xFFF59E0B)],
  ),
  AvatarPreset(
    key: 'reader',
    label: 'Bookworm',
    icon: Icons.menu_book,
    gradient: [Color(0xFF14B8A6), Color(0xFF0891B2)],
  ),
];

/// The avatar shown when a profile has no (or an unknown) `avatar_key`.
const String kDefaultAvatarKey = 'violet';

/// Resolve an `avatar_key` to its preset, falling back to the default avatar.
AvatarPreset resolveAvatar(String? avatarKey) {
  for (final preset in kAvatarPresets) {
    if (preset.key == avatarKey) return preset;
  }
  return kAvatarPresets.first;
}
