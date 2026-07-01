import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:flutter/material.dart';

Color readingStatusColor(String status) {
  return switch (status) {
    'reading' => AppColors.primary,
    'completed' => AppColors.success,
    'on_hold' || 'on-hold' => AppColors.warning,
    'plan_to_read' || 'plan' => const Color(0xFF3b82f6),
    'unread' => const Color(0xFF3b82f6).withAlpha(153),
    _ => AppColors.fg.withAlpha(51),
  };
}

String readingStatusLabel(String status) {
  return status.replaceAll('_', ' ');
}

String languageLabel(String language) {
  return switch (language.toLowerCase()) {
    'ko' => 'manhwa',
    'ja' => 'manga',
    'zh' => 'manhua',
    'en' => 'webtoon',
    _ => language.toLowerCase(),
  };
}
