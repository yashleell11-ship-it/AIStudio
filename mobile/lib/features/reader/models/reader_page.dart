import 'dart:io';

import 'package:manhwamaniacs/core/network/api_image.dart';

class ReaderPage {
  const ReaderPage({
    required this.id,
    required this.number,
    required this.imageUrl,
    this.width,
    this.height,
    this.localFile,
  });

  final String id;
  final int number;
  final String imageUrl;
  final int? width;
  final int? height;

  /// On-device chapter store resolution (1c-M3): when non-null,
  /// [ReaderPageImage] renders from this file instead of [imageUrl] — no
  /// network involved at all. Populated by
  /// `features/downloads/services/offline_reader.dart`, either as an overlay
  /// on an online-fetched chapter (bandwidth saved for already-downloaded
  /// pages) or as the sole source when the chapter was rebuilt entirely from
  /// the store because the network fetch failed.
  final File? localFile;

  double? get aspectRatio {
    final w = width;
    final h = height;
    if (w == null || h == null || h == 0) return null;
    return w / h;
  }

  ReaderPage withLocalFile(File file) => ReaderPage(
        id: id,
        number: number,
        imageUrl: imageUrl,
        width: width,
        height: height,
        localFile: file,
      );

  factory ReaderPage.fromJson(Map<String, dynamic> json, String apiBaseUrl) {
    final rawUrl = json['image_url'] as String? ?? '';
    return ReaderPage(
      id: json['id'].toString(),
      number: json['number'] as int,
      imageUrl: rawUrl.isEmpty ? '' : resolveApiResourceUrl(apiBaseUrl, rawUrl),
      width: json['width'] as int?,
      height: json['height'] as int?,
    );
  }
}
