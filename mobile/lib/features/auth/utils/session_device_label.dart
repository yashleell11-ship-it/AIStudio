/// A short, recognisable name for the device behind a session's user agent.
///
/// The point of the sessions list is answering "is one of these not me?", and
/// a raw user agent is the wrong shape for that question — every browser
/// string names three products it isn't. So the agent is reduced to the two
/// things a reader recognises: the client and the platform it ran on.
///
/// The order of the browser checks is load-bearing: Edge's agent contains
/// `Chrome` and `Safari`, Chrome's contains `Safari`, so the most specific
/// claim has to be tested first.
///
/// An agent that matches nothing is shown truncated rather than replaced with
/// "Unknown device": an unrecognised client is exactly the row worth looking
/// at, and hiding the only identifying string it carries would defeat the
/// screen.
String sessionDeviceLabel(String? userAgent) {
  final agent = userAgent?.trim() ?? '';
  if (agent.isEmpty) return 'Unknown device';
  final lower = agent.toLowerCase();

  // dio rides on dart:io's HttpClient, whose default agent is `Dart/<v>
  // (dart:io)` — so this is what every phone session looks like.
  if (lower.contains('dart')) return 'ManhwaManiacs app';

  final platform = _platform(lower);
  final browser = _browser(lower);
  if (browser != null && platform != null) return '$browser on $platform';
  if (browser != null) return browser;
  if (platform != null) return platform;
  return _truncate(agent);
}

String? _browser(String lower) {
  if (lower.contains('edg/') || lower.contains('edga/')) return 'Edge';
  if (lower.contains('opr/') || lower.contains('opera')) return 'Opera';
  if (lower.contains('firefox') || lower.contains('fxios')) return 'Firefox';
  if (lower.contains('crios') || lower.contains('chrome')) return 'Chrome';
  if (lower.contains('safari')) return 'Safari';
  return null;
}

String? _platform(String lower) {
  if (lower.contains('android')) return 'Android';
  if (lower.contains('iphone')) return 'iPhone';
  if (lower.contains('ipad')) return 'iPad';
  if (lower.contains('windows')) return 'Windows';
  // Checked after iPhone/iPad: an iOS agent also says `like Mac OS X`.
  if (lower.contains('mac os') || lower.contains('macintosh')) return 'Mac';
  if (lower.contains('cros')) return 'ChromeOS';
  if (lower.contains('linux')) return 'Linux';
  return null;
}

String _truncate(String agent) =>
    agent.length <= 40 ? agent : '${agent.substring(0, 39)}…';
