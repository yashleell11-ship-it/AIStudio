// ignore_for_file: avoid_print
//
// Turn the web app's shipped base16 themes into `AppPalette` constants.
//
//   dart run tool/themes/build_palettes.dart
//
// writes lib/app/theme/app_palettes.generated.dart
//
// ## Why it reads the web build's OUTPUT and not the base16 corpus
//
// The corpus (`tinted-theming/schemes`, 338 YAML files) is the raw material,
// but turning a 16-slot syntax palette into an app's role set is a pile of
// judgement calls — which slot leads, how far a colour may be walked before it
// stops being Nord, what a "surface" is when a third of the corpus treats
// base02 as a mid-tone highlight. The web build already made every one of
// those calls, in `frontend/scripts/themes/map.mjs`, and gated the result at
// WCAG AA.
//
// Porting that logic to Dart would mean two implementations of the same
// judgement, and the day they disagree is the day Kanagawa stops being
// Kanagawa on the phone. So this reads the web build's ARTEFACTS instead —
// `themes.generated.css` for the resolved role values and
// `themes.generated.ts` for the labels, blurbs and credits — and does only the
// work that is genuinely mobile's: renaming roles onto this app's token set,
// deriving the two tokens the web has no equivalent for, and re-gating
// everything against the floors `test/app/theme/palette_contrast_test.dart`
// enforces here.
//
// Regenerate after the web themes change. If the web files move, this fails
// loudly rather than silently shipping a stale palette set.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

// ---------------------------------------------------------------------------
// where things live
// ---------------------------------------------------------------------------

/// `<repo>/mobile/tool/themes/build_palettes.dart` → `<repo>`.
Directory _repoRoot() {
  final here = File.fromUri(Platform.script).parent; // tool/themes
  return here.parent.parent.parent; // mobile/tool → mobile → repo
}

// ---------------------------------------------------------------------------
// colour maths — a byte-for-byte match for test/support/wcag_contrast.dart,
// which is what actually judges these palettes in CI.
// ---------------------------------------------------------------------------

int _parseHex(String hex) {
  final match = RegExp(r'^#?([0-9a-fA-F]{6})$').firstMatch(hex.trim());
  if (match == null) throw FormatException('not a hex colour: $hex');
  return int.parse(match.group(1)!, radix: 16);
}

String _toHex(int rgb) =>
    '#${rgb.toRadixString(16).padLeft(6, '0').toUpperCase()}';

double _luminance(int rgb) {
  double linear(int byte) {
    final c = byte / 255.0;
    return c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4) as double;
  }

  return 0.2126 * linear((rgb >> 16) & 0xFF) +
      0.7152 * linear((rgb >> 8) & 0xFF) +
      0.0722 * linear(rgb & 0xFF);
}

double _contrast(int a, int b) {
  final la = _luminance(a);
  final lb = _luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Linear sRGB mix — `amount` of [b] into [a]. The same maths `map.mjs` uses
/// for `--mm-primary-tint`, so the two "soft" tokens are made the same way.
int _mix(int a, int b, double amount) {
  int channel(int shift) {
    final x = (a >> shift) & 0xFF;
    final y = (b >> shift) & 0xFF;
    return (x + (y - x) * amount).round().clamp(0, 255);
  }

  return (channel(16) << 16) | (channel(8) << 8) | channel(0);
}

// ---------------------------------------------------------------------------
// reading the web build
// ---------------------------------------------------------------------------

/// Every `:root[data-theme="…"]` block in `themes.generated.css`, as
/// `{ id: { '--mm-bg': '#101010', … } }`.
Map<String, Map<String, String>> _readRoles(File css) {
  final source = css.readAsStringSync();
  final blocks = RegExp(
    r':root\[data-theme="([^"]+)"\]\s*\{([^}]*)\}',
    multiLine: true,
  );
  final declaration = RegExp(r'(--[a-z0-9-]+)\s*:\s*([^;]+);');
  final out = <String, Map<String, String>>{};
  for (final block in blocks.allMatches(source)) {
    final roles = <String, String>{};
    for (final line in declaration.allMatches(block.group(2)!)) {
      roles[line.group(1)!] = line.group(2)!.trim();
    }
    out[block.group(1)!] = roles;
  }
  if (out.isEmpty) throw StateError('no theme blocks in ${css.path}');
  return out;
}

class _WebTheme {
  _WebTheme({
    required this.slug,
    required this.label,
    required this.description,
    required this.author,
    required this.isDark,
  });

  final String slug;
  final String label;
  final String description;
  final String author;
  final bool isDark;
}

/// The curated list, in the order the web ships it, from
/// `themes.generated.ts`. Reading the generated file rather than
/// `curated.mjs` means mobile can only ever offer a theme the web actually
/// ships — matching scheme-for-scheme is then structural, not a promise.
List<_WebTheme> _readCatalogue(File ts) {
  final source = ts.readAsStringSync();
  const string = r'"(?:[^"\\]|\\.)*"';
  final entry = RegExp(
    'id:\\s*($string),\\s*'
    'label:\\s*($string),\\s*'
    'description:\\s*($string),\\s*'
    'author:\\s*($string),\\s*'
    'scheme:\\s*($string),',
  );
  String text(Match m, int group) => jsonDecode(m.group(group)!) as String;
  final themes = [
    for (final m in entry.allMatches(source))
      _WebTheme(
        slug: text(m, 1),
        label: text(m, 2),
        description: text(m, 3),
        author: text(m, 4),
        isDark: text(m, 5) == 'dark',
      ),
  ];
  if (themes.isEmpty) throw StateError('no theme entries in ${ts.path}');
  return themes;
}

// ---------------------------------------------------------------------------
// web roles → mobile tokens
// ---------------------------------------------------------------------------

/// Mobile ids for schemes that already shipped here under a different name.
///
/// A palette id is persisted per profile (`mm.theme.u{user}p{profile}`), so
/// renaming one silently resets somebody's theme. These eight hand-written
/// palettes are being REPLACED by their generated twin — same scheme, now
/// derived by the same mapper the web uses — and they keep their old id so the
/// stored preference keeps resolving to the theme it always named.
///
/// `gruvbox` points at the HARD variant because that is the ground the shipped
/// hand-written palette used (#1D2021); the medium variant ships alongside it
/// under its own id.
const Map<String, String> _legacyIds = {
  'nord': 'nord',
  'dracula': 'dracula',
  'catppuccin-mocha': 'mocha',
  'gruvbox-dark-hard': 'gruvbox',
  'rose-pine': 'rose_pine',
  'everforest-dark-hard': 'everforest',
  'catppuccin-latte': 'latte',
  'rose-pine-dawn': 'dawn',
};

/// Ids owned by the hand-written palettes in `app_palettes.dart`, which the
/// generated set must never collide with.
const Set<String> _houseIds = {
  'eclipse',
  'amoled',
  'tokyo_night',
  'solarized_dark',
  'solarized_light',
  'daylight',
  'paper',
};

class _Palette {
  _Palette(this.web, this.id, this.tokens);

  final _WebTheme web;
  final String id;
  final Map<String, int> tokens;

  int operator [](String token) => tokens[token]!;
}

/// The mobile token set, named from the web's roles.
///
/// Two tokens have no web counterpart and are derived here:
///
///  * `surface2` — the web's card/sheet ramp is two steps (`--mm-surface`,
///    `--mm-elevated`); mobile's is three, and every shipped hand-written
///    palette already sets `surface2` and `surfaceElevated` to the same value.
///    Kept identical rather than inventing a fourth grey.
///  * `accentSoft` — the softer companion to `accent`, which mobile spends on
///    secondary highlights. Built with the exact recipe `map.mjs` uses for
///    `--mm-primary-tint` (30% along the scheme's own ramp toward
///    `--mm-contrast-bg`, its far end), so the two "soft" tokens are siblings
///    and both inherit their base's already-gated contrast rather than
///    borrowing an ungated slot like `--mm-accent-warm`.
_Palette _toMobile(_WebTheme web, Map<String, String> roles) {
  int role(String name) {
    final value = roles[name];
    if (value == null) throw StateError('${web.slug} has no $name');
    return _parseHex(value);
  }

  final accent = role('--mm-accent');
  final rampEnd = role('--mm-contrast-bg');

  final id = _legacyIds[web.slug] ?? web.slug.replaceAll('-', '_');
  if (_houseIds.contains(id)) {
    throw StateError('generated id "$id" collides with a hand-written palette');
  }

  return _Palette(web, id, {
    'bg': role('--mm-bg'),
    'surface': role('--mm-surface'),
    'surface2': role('--mm-elevated'),
    'surfaceElevated': role('--mm-elevated'),
    'fg': role('--mm-fg'),
    'muted': role('--mm-muted'),
    'primary': role('--mm-primary'),
    'primaryHover': role('--mm-primary-hover'),
    'primaryFg': role('--mm-primary-fg'),
    'primarySoft': role('--mm-primary-tint'),
    'accent': accent,
    'accentSoft': _mix(accent, rampEnd, 0.3),
    'accentFg': role('--mm-accent-fg'),
    'danger': role('--mm-danger'),
    'success': role('--mm-success'),
    'warning': role('--mm-warning'),
  });
}

// ---------------------------------------------------------------------------
// the gate — the same pairings and floors palette_contrast_test.dart asserts
// ---------------------------------------------------------------------------

const double _bodyFloor = 4.5;
const double _accentFloor = 3.0;

class _Verdict {
  _Verdict(this.failures, this.worst, this.worstPairing);

  final List<String> failures;
  final double worst;
  final String worstPairing;

  bool get ok => failures.isEmpty;
}

_Verdict _gate(_Palette p) {
  final failures = <String>[];
  var worst = double.infinity;
  var worstPairing = '';

  void check(String pairing, int fg, int bg, double floor) {
    final ratio = _contrast(fg, bg);
    if (ratio < worst) {
      worst = ratio;
      worstPairing = pairing;
    }
    if (ratio < floor) {
      failures.add('$pairing ${ratio.toStringAsFixed(2)}:1 < $floor:1');
    }
  }

  const surfaces = ['bg', 'surface', 'surface2', 'surfaceElevated'];
  for (final surface in surfaces) {
    check('fg on $surface', p['fg'], p[surface], _bodyFloor);
    check('muted on $surface', p['muted'], p[surface], _accentFloor);
  }
  for (final token in [
    'primary',
    'primarySoft',
    'accent',
    'accentSoft',
    'danger',
    'success',
    'warning',
  ]) {
    check('$token on bg', p[token], p['bg'], _accentFloor);
    check('$token on surface', p[token], p['surface'], _accentFloor);
  }
  check('primaryFg on primary', p['primaryFg'], p['primary'], _bodyFloor);
  check('accentFg on accent', p['accentFg'], p['accent'], _bodyFloor);

  // Not a contrast floor but the thing that makes a sheet on a card on a page
  // read as three layers: elevation has to keep climbing away from the page.
  if (_contrast(p['surface'], p['bg']) <= 1.01) {
    failures.add('surface does not step away from the page');
  }
  if (_contrast(p['surfaceElevated'], p['bg']) <
      _contrast(p['surface'], p['bg'])) {
    failures.add('elevated sits below surface');
  }

  return _Verdict(failures, worst, worstPairing);
}

// ---------------------------------------------------------------------------
// emit
// ---------------------------------------------------------------------------

/// `catppuccin-macchiato` → `catppuccinMacchiato`.
String _dartName(String id) {
  final parts = id.split(RegExp('[-_]'));
  return parts.first +
      parts
          .skip(1)
          .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
          .join();
}

/// A Dart string literal that `prefer_single_quotes` is happy with — double
/// quotes only where the text itself holds an apostrophe ("GitHub's own dark
/// mode"), which is exactly when the lint allows them.
String _dartString(String value) {
  if (value.contains("'") && !value.contains('"')) return '"$value"';
  return "'${value.replaceAll(r'\', r'\\').replaceAll("'", r"\'")}'";
}

String _color(int rgb) =>
    'Color(0xFF${rgb.toRadixString(16).padLeft(6, '0').toUpperCase()})';

const List<String> _tokenOrder = [
  'bg',
  'surface',
  'surface2',
  'surfaceElevated',
  'fg',
  'muted',
  'primary',
  'primaryHover',
  'primaryFg',
  'primarySoft',
  'accent',
  'accentSoft',
  'accentFg',
  'danger',
  'success',
  'warning',
];

String _emit(List<_Palette> palettes, String revision) {
  final buffer = StringBuffer()
    ..writeln('// GENERATED by tool/themes/build_palettes.dart — do not edit.')
    ..writeln('//')
    ..writeln('// Source:     tinted-theming/schemes @ $revision')
    ..writeln('// Mapped by:  frontend/scripts/themes/map.mjs (via its output)')
    ..writeln('// Regenerate: dart run tool/themes/build_palettes.dart')
    ..writeln("import 'package:flutter/material.dart';")
    ..writeln("import 'package:manhwamaniacs/app/theme/app_palette.dart';")
    ..writeln()
    ..writeln('/// The base16 palettes, converted from the set the web app')
    ..writeln('/// ships so a scheme wears the same colours on both.')
    ..writeln('///')
    ..writeln('/// Every entry cleared the floors in')
    ..writeln('/// `test/app/theme/palette_contrast_test.dart` at generation')
    ..writeln('/// time; the suite re-checks them on every run.')
    ..writeln('abstract final class Base16Palettes {');

  for (final p in palettes) {
    final verdict = _gate(p);
    buffer
      ..writeln('  /// ${p.web.label} — ${p.web.author}.')
      ..writeln('  ///')
      ..writeln('  /// ${p.web.description}')
      ..writeln('  ///')
      ..writeln(
        '  /// Worst pairing: ${verdict.worstPairing} at '
        '${verdict.worst.toStringAsFixed(2)}:1.',
      )
      ..writeln('  static const AppPalette ${_dartName(p.id)} = AppPalette(')
      ..writeln('    id: ${_dartString(p.id)},')
      ..writeln('    name: ${_dartString(p.web.label)},')
      ..writeln('    description: ${_dartString(p.web.description)},')
      ..writeln('    author: ${_dartString(p.web.author)},')
      ..writeln(
        '    brightness: Brightness.${p.web.isDark ? 'dark' : 'light'},',
      );
    for (final token in _tokenOrder) {
      buffer.writeln('    $token: ${_color(p[token])},');
    }
    buffer
      ..writeln('  );')
      ..writeln();
  }

  void list(String name, String doc, Iterable<_Palette> entries) {
    buffer
      ..writeln('  /// $doc')
      ..writeln('  static const List<AppPalette> $name = [');
    for (final p in entries) {
      buffer.writeln('    ${_dartName(p.id)},');
    }
    buffer
      ..writeln('  ];')
      ..writeln();
  }

  list(
    'dark',
    'Dark schemes, in the order the web curates them (families adjacent).',
    palettes.where((p) => p.web.isDark),
  );
  list(
    'light',
    'Light schemes, same order.',
    palettes.where((p) => !p.web.isDark),
  );

  buffer.writeln('}');
  return buffer.toString();
}

// ---------------------------------------------------------------------------

void main(List<String> args) {
  final root = _repoRoot();
  final css = File(
    '${root.path}/frontend/src/app/themes.generated.css',
  );
  final ts = File(
    '${root.path}/frontend/src/features/preferences/themes.generated.ts',
  );
  for (final file in [css, ts]) {
    if (!file.existsSync()) {
      stderr.writeln(
        'missing ${file.path}\n'
        'The web theme build has to have run first: '
        '(cd frontend && node scripts/themes/build-themes.mjs)',
      );
      exitCode = 1;
      return;
    }
  }

  final revision =
      RegExp(r'Revision:\s*(\S+)').firstMatch(ts.readAsStringSync())?.group(1) ??
          'unknown';
  final roles = _readRoles(css);
  final catalogue = _readCatalogue(ts);

  final kept = <_Palette>[];
  final dropped = <String, List<String>>{};
  for (final web in catalogue) {
    final block = roles[web.slug];
    if (block == null) {
      dropped[web.slug] = ['no CSS block — the web build is out of step'];
      continue;
    }
    final palette = _toMobile(web, block);
    final verdict = _gate(palette);
    if (!verdict.ok) {
      dropped[web.slug] = verdict.failures;
      continue;
    }
    kept.add(palette);
  }

  final ids = kept.map((p) => p.id).toList();
  if (ids.toSet().length != ids.length) {
    throw StateError('duplicate generated ids: $ids');
  }
  for (final legacy in _legacyIds.values) {
    if (!ids.contains(legacy)) {
      throw StateError(
        'legacy id "$legacy" is not in the generated set — a stored theme '
        'preference would silently reset to Eclipse',
      );
    }
  }

  final out = File('${root.path}/mobile/lib/app/theme/app_palettes.generated.dart');
  out.writeAsStringSync(_emit(kept, revision));

  final darks = kept.where((p) => p.web.isDark).length;
  print(
    'palettes: ${kept.length} generated ($darks dark, ${kept.length - darks} '
    'light) from ${catalogue.length} web themes → ${out.path}',
  );
  for (final entry in dropped.entries) {
    print('  dropped ${entry.key}: ${entry.value.join('; ')}');
  }
  if (args.contains('--report')) {
    for (final p in kept) {
      final verdict = _gate(p);
      print(
        '  ${p.id.padRight(28)} ${verdict.worst.toStringAsFixed(2)}:1  '
        '${verdict.worstPairing} (${_toHex(p['bg'])})',
      );
    }
  }
}
