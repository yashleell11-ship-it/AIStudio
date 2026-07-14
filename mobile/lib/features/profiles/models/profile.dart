import 'package:manhwamaniacs/features/profiles/models/mood.dart';

/// A per-user reading persona (Netflix-style). Mirrors the backend
/// `/profiles` serialisation 1-to-1. Immutable.
class Profile {
  const Profile({
    required this.id,
    required this.name,
    required this.avatarKey,
    required this.mood,
    required this.sortOrder,
    required this.createdAt,
  });

  final int id;
  final String name;

  /// References an avatar in [kAvatarPresets]; may be null for legacy rows.
  final String? avatarKey;
  final Mood mood;
  final int sortOrder;
  final DateTime createdAt;

  factory Profile.fromJson(Map<String, dynamic> json) => Profile(
        id: json['id'] as int,
        name: json['name'] as String,
        avatarKey: json['avatar_key'] as String?,
        mood: Mood.fromWire(json['mood'] as String?),
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  /// Reduce to the lightweight snapshot persisted as the active selection.
  ActiveProfile toSnapshot() => ActiveProfile(
        id: id,
        name: name,
        avatarKey: avatarKey,
        mood: mood,
      );
}

/// Hard cap on profiles per account, enforced in the UI (matches the backend).
const int kMaxProfiles = 5;

/// The minimal snapshot of the active profile kept on-device (persisted to
/// shared preferences). Enough to tint the shell and label the switcher without
/// re-fetching the list on every screen.
class ActiveProfile {
  const ActiveProfile({
    required this.id,
    required this.name,
    required this.avatarKey,
    required this.mood,
  });

  final int id;
  final String name;
  final String? avatarKey;
  final Mood mood;

  factory ActiveProfile.fromJson(Map<String, dynamic> json) => ActiveProfile(
        id: json['id'] as int,
        name: json['name'] as String,
        avatarKey: json['avatar_key'] as String?,
        mood: Mood.fromWire(json['mood'] as String?),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'avatar_key': avatarKey,
        'mood': mood.wire,
      };
}
