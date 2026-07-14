/// Spacing constants matching Tailwind's default scale (4px base unit).
abstract final class AppSpacing {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xl2 = 24;
  static const double xl3 = 32;
  static const double xl4 = 40;
  static const double xl5 = 48;
  static const double xl6 = 64;
  static const double xl7 = 80;
}

/// Border radius constants — Eclipse Warm uses pills + large soft cards.
abstract final class AppRadius {
  static const double xs = 4;
  static const double sm = 6;
  static const double md = 10;
  static const double lg = 14;
  static const double xl = 20;
  static const double xl2 = 28;

  /// Large card radius (40px) — matches web large-card intent.
  static const double xl3 = 40;

  /// Extra-large hero/card radius (60px).
  static const double xl4 = 60;

  /// Fully rounded pill (999) — buttons, chips, tags.
  static const double pill = 999;
  static const double full = 9999;
}
