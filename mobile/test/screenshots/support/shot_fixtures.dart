import 'package:manhwamaniacs/features/library/models/followed_series.dart';

/// The invented library the marketing screenshots are taken of.
///
/// Every title here is made up. That is the point, and it is a hard
/// requirement rather than a convenience: the install page is the public front
/// door, the app carries 59 mature sources, and the only way to guarantee none
/// of them — or their series, or their artwork — reaches that page is for the
/// screenshots to be taken of data that exists nowhere but this file.
///
/// The titles are deliberately plausible and plainly general-audience, so the
/// shelf reads as a real library without borrowing anyone's.
class ShotSeries {
  const ShotSeries({
    required this.title,
    required this.chapterCount,
    required this.status,
    this.favorite = false,
    this.author,
    this.blurb,
  });

  final String title;
  final int chapterCount;
  final String status;
  final bool favorite;
  final String? author;
  final String? blurb;

  String get slug => title
      .toLowerCase()
      .replaceAll(RegExp(r"[^a-z0-9]+"), '-')
      .replaceAll(RegExp(r'^-|-$'), '');
}

const shotBaseUrl = 'http://127.0.0.1:8000';

/// Cover path for [series] — the backend's own proxy route, so the app builds
/// the request exactly as it does in production (including the `?w=` the
/// route understands).
String shotCoverPath(ShotSeries series) =>
    '/sources/shelf/series/${series.slug}/cover';

const shotManga = <ShotSeries>[
  ShotSeries(
      title: 'The Lantern Courier',
      chapterCount: 128,
      status: 'reading',
      favorite: true),
  ShotSeries(
      title: 'Sword of the Ninth Spring',
      chapterCount: 246,
      status: 'reading'),
  ShotSeries(
      title: 'Skyward Gardeners', chapterCount: 74, status: 'plan_to_read'),
  ShotSeries(
      title: 'Paper Tiger Academy',
      chapterCount: 311,
      status: 'reading',
      favorite: true),
  ShotSeries(
      title: "The Cartographer's Apprentice",
      chapterCount: 96,
      status: 'reading'),
  ShotSeries(title: 'Moonlit Bakery', chapterCount: 152, status: 'completed'),
  ShotSeries(title: 'Iron Kite', chapterCount: 63, status: 'reading'),
  ShotSeries(
      title: 'Tea House on Rain Street',
      chapterCount: 208,
      status: 'reading',
      favorite: true),
  ShotSeries(title: 'The Quiet Duelist', chapterCount: 187, status: 'reading'),
];

const shotNovels = <ShotSeries>[
  ShotSeries(
    title: 'The Salt Road Chronicles',
    chapterCount: 412,
    status: 'reading',
    favorite: true,
    author: 'M. Aldarion',
    blurb: 'A caravan clerk inherits a map nobody was meant to finish.',
  ),
  ShotSeries(
    title: 'Notes from the Ninth Tower',
    chapterCount: 188,
    status: 'reading',
    author: 'H. Verren',
    blurb: 'Letters home from an apprentice who keeps climbing.',
  ),
  ShotSeries(
    title: 'A Winter of Small Machines',
    chapterCount: 96,
    status: 'plan_to_read',
    author: 'Ren Okabe',
    blurb: 'The clockmaker’s daughter builds one more spring.',
  ),
  ShotSeries(
    title: 'The Orchard Beneath',
    chapterCount: 254,
    status: 'reading',
    author: 'S. Marlowe',
    blurb: 'Every root in the valley remembers a different summer.',
  ),
  ShotSeries(
    title: 'Harbourmaster',
    chapterCount: 331,
    status: 'reading',
    author: 'D. Ferris',
    blurb: 'Nothing leaves this port without her signature.',
  ),
  ShotSeries(
    title: 'Copper for the Ferryman',
    chapterCount: 147,
    status: 'completed',
    author: 'A. Iyer',
    blurb: 'A ledger of debts, and one that was never paid.',
  ),
  ShotSeries(
    title: 'The Long Quiet Country',
    chapterCount: 208,
    status: 'reading',
    author: 'Wren Halloway',
    blurb: 'Two hundred miles of road and one letter to deliver.',
  ),
];

/// Builds the follow rows the Library tab and browse screen render.
List<FollowedSeries> shotFollowed(List<ShotSeries> series) => [
      for (var i = 0; i < series.length; i++)
        FollowedSeries(
          id: i + 1,
          sourceId: 'shelf',
          seriesKey: series[i].slug,
          title: series[i].title,
          coverUrl: shotCoverPath(series[i]),
          isFavorite: series[i].favorite,
          readingStatus: series[i].status,
          notify: true,
          sortOrder: i,
          contentRating: 'safe',
          rating: 'safe',
          chapterCount: series[i].chapterCount,
          createdAt: DateTime.utc(2026, 3, 1).add(Duration(days: i * 9)),
          updatedAt: DateTime.utc(2026, 8, 20).add(Duration(hours: i * 5)),
        ),
    ];
