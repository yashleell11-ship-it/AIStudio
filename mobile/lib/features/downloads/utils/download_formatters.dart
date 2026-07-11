String formatDownloadBytes(int value) {
  if (value < 1024) return '$value B';
  if (value < 1024 * 1024) return '${(value / 1024).toStringAsFixed(1)} KB';
  if (value < 1024 * 1024 * 1024) {
    return '${(value / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
  return '${(value / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
}

String formatDownloadSpeed(double? speedBps, double? speedMbps) {
  if (speedMbps != null && speedMbps > 0) {
    return '${speedMbps.toStringAsFixed(1)} MB/s';
  }
  if (speedBps == null || speedBps <= 0) return '—';
  return '${formatDownloadBytes(speedBps.round())}/s';
}

String formatDownloadEta(double? seconds) {
  if (seconds == null || seconds <= 0) return '—';
  final total = seconds.round();
  if (total < 60) return '${total}s';
  final minutes = total ~/ 60;
  final remainder = total % 60;
  return '${minutes}m ${remainder}s';
}

String downloadStatusLabel(String status) {
  if (status == 'failed') return 'Error';
  if (status.isEmpty) return status;
  return status[0].toUpperCase() + status.substring(1);
}

String seriesInitials(String title) {
  final words = title.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
  if (words.isEmpty) return '?';
  if (words.length == 1) return words.first.substring(0, words.first.length.clamp(0, 2)).toUpperCase();
  return '${words[0][0]}${words[1][0]}'.toUpperCase();
}
