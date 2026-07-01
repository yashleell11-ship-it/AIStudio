class ReaderPage {
  const ReaderPage({
    required this.id,
    required this.number,
    required this.imageUrl,
    this.width,
    this.height,
  });

  final String id;
  final int number;
  final String imageUrl;
  final int? width;
  final int? height;

  double? get aspectRatio {
    final w = width;
    final h = height;
    if (w == null || h == null || h == 0) return null;
    return w / h;
  }

  factory ReaderPage.fromJson(Map<String, dynamic> json, String apiBaseUrl) {
    final rawUrl = json['image_url'] as String;
    final imageUrl =
        rawUrl.startsWith('http') ? rawUrl : '$apiBaseUrl$rawUrl';
    return ReaderPage(
      id: json['id'].toString(),
      number: json['number'] as int,
      imageUrl: imageUrl,
      width: json['width'] as int?,
      height: json['height'] as int?,
    );
  }
}
