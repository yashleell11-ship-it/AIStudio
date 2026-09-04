/// The real image format of a downloaded page, sniffed from its own leading
/// bytes.
///
/// Blobs are named by their sha256 and carry **no extension at all** (see
/// [BlobStore]), and the connector-supplied URL that produced them is long
/// gone by the time an export runs. Sources also lie: a `.jpg` URL serving
/// WebP is routine on the madara-family sites this app reads. So the bytes
/// are the only honest answer to "what should this file be called on disk",
/// and an export that guesses wrong produces a folder of images the Files
/// app refuses to preview — exactly the failure this whole feature exists to
/// avoid.
enum PageImageType {
  jpeg('.jpg'),
  png('.png'),
  gif('.gif'),
  webp('.webp'),
  avif('.avif'),
  heic('.heic'),
  bmp('.bmp'),

  /// Nothing matched. Exported with a neutral extension rather than dropped:
  /// a page the store holds is a page the user downloaded, and handing it
  /// over unlabelled beats silently omitting it from their export.
  unknown('.img');

  const PageImageType(this.extension);

  /// Includes the leading dot, ready to concatenate onto a file stem.
  final String extension;
}

/// How many leading bytes [sniffPageImageType] ever inspects — enough for the
/// longest signature it knows (an ISO-BMFF `ftyp` brand, which sits at bytes
/// 4..12).
const int kPageImageSniffLength = 16;

/// Identifies [header] (the first [kPageImageSniffLength] bytes of a page
/// blob, or fewer at end of file) by magic number.
PageImageType sniffPageImageType(List<int> header) {
  bool startsWith(List<int> signature, {int at = 0}) {
    if (header.length < at + signature.length) return false;
    for (var i = 0; i < signature.length; i++) {
      if (header[at + i] != signature[i]) return false;
    }
    return true;
  }

  if (startsWith(const [0xFF, 0xD8, 0xFF])) return PageImageType.jpeg;
  if (startsWith(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) {
    return PageImageType.png;
  }
  if (startsWith(const [0x47, 0x49, 0x46, 0x38])) return PageImageType.gif;
  if (startsWith(const [0x42, 0x4D])) return PageImageType.bmp;
  // RIFF....WEBP — the four size bytes between the two tags are skipped.
  if (startsWith(const [0x52, 0x49, 0x46, 0x46]) &&
      startsWith(const [0x57, 0x45, 0x42, 0x50], at: 8)) {
    return PageImageType.webp;
  }

  // ISO base media (`....ftyp<brand>`): AVIF and HEIC share the container and
  // differ only by brand, so the brand is what has to be read.
  if (startsWith(const [0x66, 0x74, 0x79, 0x70], at: 4) && header.length >= 12) {
    final brand = String.fromCharCodes(header.sublist(8, 12));
    if (brand == 'avif' || brand == 'avis') return PageImageType.avif;
    if (brand == 'heic' ||
        brand == 'heix' ||
        brand == 'heim' ||
        brand == 'heis' ||
        brand == 'hevc' ||
        brand == 'mif1' ||
        brand == 'msf1') {
      return PageImageType.heic;
    }
  }

  return PageImageType.unknown;
}
