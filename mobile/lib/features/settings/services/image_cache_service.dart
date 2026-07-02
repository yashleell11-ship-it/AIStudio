import 'dart:io';

import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:path_provider/path_provider.dart';

/// Reads and clears the on-disk image cache used by `cached_network_image`
/// (via `flutter_cache_manager`'s [DefaultCacheManager]) throughout the app
/// — reader pages, covers, thumbnails. Behind an interface so Settings
/// widgets/providers can be tested without touching the real filesystem.
abstract interface class ImageCacheService {
  /// Total bytes currently used by the on-disk image cache.
  Future<int> getCacheSizeBytes();

  /// Deletes every cached image. Safe to call even when the cache is empty.
  Future<void> clear();
}

class ImageCacheServiceImpl implements ImageCacheService {
  const ImageCacheServiceImpl();

  @override
  Future<int> getCacheSizeBytes() async {
    final dir = await _cacheDirectory();
    if (dir == null || !dir.existsSync()) return 0;
    var total = 0;
    await for (final entity in dir.list(recursive: true, followLinks: false)) {
      if (entity is File) {
        try {
          total += await entity.length();
        } on FileSystemException {
          // File may have been deleted concurrently by the cache manager.
        }
      }
    }
    return total;
  }

  @override
  Future<void> clear() async {
    await DefaultCacheManager().emptyCache();
  }

  Future<Directory?> _cacheDirectory() async {
    try {
      final tempDir = await getTemporaryDirectory();
      final cacheDir = Directory('${tempDir.path}/libCachedImageData');
      return cacheDir;
    } on MissingPlatformDirectoryException {
      return null;
    }
  }
}
