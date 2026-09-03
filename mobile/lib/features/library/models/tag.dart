import 'package:flutter/painting.dart';

class Tag {
  const Tag({
    required this.id,
    required this.name,
    required this.category,
    this.colorHex,
  });

  final int id;
  final String name;
  final String category;
  final String? colorHex;

  Color? get color {
    final hex = colorHex;
    if (hex == null) return null;
    final clean = hex.replaceFirst('#', '');
    final value = int.tryParse(clean, radix: 16);
    return value != null ? Color(0xFF000000 | value) : null;
  }

  factory Tag.fromJson(Map<String, dynamic> json) => Tag(
        id: json['id'] as int,
        name: json['name'] as String,
        category: json['category'] as String,
        colorHex: json['color'] as String?,
      );
}
