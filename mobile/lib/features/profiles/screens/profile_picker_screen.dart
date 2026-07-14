import 'dart:ui' show ImageFilter, lerpDouble;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/profile_animations.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/widgets/mood_backdrop.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_avatar.dart';
import 'package:manhwamaniacs/shared/widgets/async_value_widget.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';

/// Netflix-style profile picker (route `/profiles`). Doubles as the management
/// surface: a "Manage" toggle switches taps from *select* to *edit*.
///
/// Reached two ways — as the post-auth gate (an authenticated visitor with no
/// active profile) and from the app-bar switcher chip to change profiles.
///
/// Selection plays a single, staged full-screen ceremony (see
/// [ProfileSelectPhases]): the other profiles blur and dim, the chosen tile
/// lifts, then the profile's mood floods edge-to-edge from the tapped tile and
/// holds before the app enters home. The active profile is committed only when
/// the animation finishes — committing it flips [activeProfileProvider], which
/// rebuilds the router into the home shell whose backdrop already shows the
/// same mood, so the tint never pops back to neutral. Under reduced motion the
/// whole ceremony collapses to an instant select + navigate.
class ProfilePickerScreen extends ConsumerStatefulWidget {
  const ProfilePickerScreen({super.key});

  @override
  ConsumerState<ProfilePickerScreen> createState() =>
      _ProfilePickerScreenState();
}

class _ProfilePickerScreenState extends ConsumerState<ProfilePickerScreen>
    with SingleTickerProviderStateMixin {
  /// Drives the whole selection ceremony (0→1). Idle at 0 until a pick starts.
  late final AnimationController _controller;

  /// The profile mid-selection (drives the focus/dim/flood animation). `null`
  /// while the picker is idle.
  Profile? _selecting;

  /// Global position of the tap that started the selection — the mood flood
  /// originates here so it appears to grow out of the tapped avatar.
  Offset? _tapOrigin;

  /// Whether taps edit a profile instead of selecting it.
  bool _manage = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: kProfileSelectionDuration,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _select(Profile profile) async {
    if (_selecting != null) return;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    setState(() => _selecting = profile);

    if (reduceMotion) {
      await ref.read(activeProfileProvider.notifier).select(profile);
      if (!mounted) return;
      ref.read(profileSessionReadyProvider.notifier).enter();
      context.go(Routes.home);
      return;
    }

    // Play the full ceremony *before* committing. While the active profile is
    // unchanged the router is not rebuilt, so the picker stays mounted for the
    // entire animation instead of being torn down the instant we select.
    await _controller.forward(from: 0);
    if (!mounted) return;

    // Commit now — this adopts the mood on the app shell and rebuilds the
    // router into home, seamlessly from the flood's settled end-state.
    await ref.read(activeProfileProvider.notifier).select(profile);
    if (!mounted) return;
    ref.read(profileSessionReadyProvider.notifier).enter();
    context.go(Routes.home);
  }

  void _edit(Profile profile) {
    context.push(ProfileRoutes.edit(profile.id));
  }

  @override
  Widget build(BuildContext context) {
    final profilesAsync = ref.watch(profilesProvider);
    final active = ref.watch(activeProfileProvider);
    final backdropMood = _selecting?.mood ?? active?.mood ?? Mood.neutral;

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final v = _controller.value;
        final focus = ProfileSelectPhases.focus.transform(v);
        final expand = ProfileSelectPhases.expand.transform(v);
        final identity = ProfileSelectPhases.identity.transform(v);
        final handoff = ProfileSelectPhases.handoff.transform(v);
        final selecting = _selecting != null;

        return MoodBackdrop(
          mood: backdropMood,
          variant: MoodBackdropVariant.picker,
          // A Stack lets the chosen mood flood the entire viewport during the
          // ceremony, above the picker, so the pick reads as the mood taking
          // over the whole screen before it hands off to the app shell.
          child: Stack(
            children: [
              Scaffold(
                backgroundColor: Colors.transparent,
                appBar: AppBar(
                  backgroundColor: Colors.transparent,
                  // The Manage affordance is meaningless mid-selection — hide it
                  // so nothing floats over the takeover.
                  actions: selecting
                      ? const []
                      : [
                          AsyncValueWidget(
                            value: profilesAsync,
                            loading: const SizedBox.shrink(),
                            error: (_) => const SizedBox.shrink(),
                            data: (profiles) => profiles.isEmpty
                                ? const SizedBox.shrink()
                                : TextButton(
                                    onPressed: () =>
                                        setState(() => _manage = !_manage),
                                    child: Text(_manage ? 'Done' : 'Manage'),
                                  ),
                          ),
                        ],
                ),
                body: SafeArea(
                  child: AsyncValueWidget(
                    value: profilesAsync,
                    data: (profiles) => _PickerBody(
                      profiles: profiles,
                      selectingId: _selecting?.id,
                      focus: focus,
                      manage: _manage,
                      onSelect: _select,
                      onSelectAt: (offset) => _tapOrigin = offset,
                      onEdit: _edit,
                      onAdd: () => context.push(ProfileRoutes.create),
                    ),
                  ),
                ),
              ),
              if (selecting)
                Positioned.fill(
                  child: _MoodTakeover(
                    key: const Key('profile-mood-takeover'),
                    mood: backdropMood,
                    profile: _selecting!,
                    origin: _originAlignment(context),
                    expand: expand,
                    identity: identity,
                    handoff: handoff,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  /// Convert the recorded tap position into a gradient [Alignment]. Falls back
  /// to the centre when the selection wasn't started by a pointer (e.g. a
  /// keyboard activation).
  Alignment _originAlignment(BuildContext context) {
    final origin = _tapOrigin;
    if (origin == null) return Alignment.center;
    final size = MediaQuery.sizeOf(context);
    if (size.isEmpty) return Alignment.center;
    return Alignment(
      (origin.dx / size.width) * 2 - 1,
      (origin.dy / size.height) * 2 - 1,
    );
  }
}

/// Full-screen mood flood shown during a selection. It blooms out of the tapped
/// tile ([origin]) to fill the viewport, holds the chosen profile's identity at
/// centre, then settles onto the app-shell backdrop so the handoff into home is
/// seamless. Driven entirely by the parent controller's phase fractions.
class _MoodTakeover extends StatelessWidget {
  const _MoodTakeover({
    super.key,
    required this.mood,
    required this.profile,
    required this.origin,
    required this.expand,
    required this.identity,
    required this.handoff,
  });

  final Mood mood;
  final Profile profile;
  final Alignment origin;

  /// Linear 0→1 across the expand phase (flood growth + opacity).
  final double expand;

  /// Linear 0→1 across the identity phase (centre avatar + name fade).
  final double identity;

  /// Linear 0→1 across the handoff phase (settle onto the shell backdrop).
  final double handoff;

  @override
  Widget build(BuildContext context) {
    const base = ProfileMoodColors.base;
    final e = ProfileSelectCurves.bloom.transform(expand);
    final settle = ProfileSelectCurves.settle.transform(handoff);
    final tinted = mood.isTinted;

    // Fade the flood in a touch ahead of its growth so the screen is solidly
    // covered before the identity and handoff phases run.
    final fill = Curves.easeOut.transform((expand * 1.45).clamp(0.0, 1.0));

    // A three-stop bloom gives the flood dimensional depth instead of a flat
    // wash: a warm glowing core, the mood mid-tone, then base. The mixes start
    // rich and cinematic, then ease toward the softer shell tint (MoodBackdrop
    // .shell mixes at 0.24) during the handoff so the last frame matches home
    // and the tint never resets.
    final coreRatio = lerpDouble(0.92, 0.26, settle)!;
    final midRatio = lerpDouble(0.48, 0.13, settle)!;
    final core = tinted ? Color.lerp(base, mood.tint, coreRatio)! : base;
    // A whisper of amber warmth in the very core early on, gone by handoff.
    final warmCore = tinted
        ? Color.lerp(core, AppColors.accentAmber, lerpDouble(0.14, 0.0, settle)!)!
        : base;
    final mid = tinted ? Color.lerp(base, mood.tint, midRatio)! : base;

    // Bloom origin drifts from the tapped tile toward the shell's top-anchored
    // glow, and the radius grows past the viewport, so the flood both expands
    // and lands where the app-shell backdrop expects it.
    final bloomCenter = Alignment.lerp(origin, const Alignment(0, -0.6), e)!;
    final center = Alignment.lerp(bloomCenter, const Alignment(0, -0.95), settle)!;
    final radius = lerpDouble(lerpDouble(0.26, 1.45, e), 1.25, settle)!;
    final midStop = lerpDouble(0.30, 0.55, e)!;
    final edgeStop = lerpDouble(0.58, 0.9, e)!;

    // A soft vignette darkens the edges as the flood lands, lending the takeover
    // a cinematic depth-of-field. It eases lighter on handoff so it flattens
    // into the shell rather than lingering as a hard frame.
    final vignette =
        Curves.easeOut.transform(expand.clamp(0.0, 1.0)) * lerpDouble(0.5, 0.26, settle)!;

    // "Who's reading" identity: fade up over the flood, then fade back out on
    // handoff so the final frame is pure mood — identical to the shell.
    final idIn = ProfileSelectCurves.identityIn.transform(identity);
    final idOpacity = Curves.easeOut.transform(identity) *
        (1 - Curves.easeIn.transform(handoff));
    final idScale = lerpDouble(0.82, 1.0, idIn)!;
    // Soft blur-in: the avatar + name resolve out of a gentle gaussian as they
    // settle at centre, so the reveal breathes instead of snapping in.
    final idBlur = lerpDouble(16.0, 0.0, idIn)!;

    Widget identityColumn = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ProfileAvatar(
          avatarKey: profile.avatarKey,
          size: 132,
          ringColor: AppColors.accentAmber,
        ),
        const SizedBox(height: AppSpacing.lg),
        Text(
          profile.name,
          textAlign: TextAlign.center,
          style: AppTypography.h2,
        ),
      ],
    );
    if (idBlur > 0.1) {
      identityColumn = ImageFiltered(
        imageFilter: ImageFilter.blur(
          sigmaX: idBlur,
          sigmaY: idBlur,
          tileMode: TileMode.decal,
        ),
        child: identityColumn,
      );
    }

    return IgnorePointer(
      child: Opacity(
        opacity: fill,
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: base,
                gradient: RadialGradient(
                  center: center,
                  radius: radius,
                  colors: [warmCore, mid, base],
                  stops: [0.0, midStop, edgeStop],
                ),
              ),
            ),
            if (vignette > 0.01)
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    radius: 1.1,
                    colors: [
                      Colors.transparent,
                      Colors.black.withValues(alpha: vignette.clamp(0.0, 1.0)),
                    ],
                    stops: const [0.55, 1.0],
                  ),
                ),
              ),
            if (idOpacity > 0.01)
              Center(
                child: Opacity(
                  opacity: idOpacity.clamp(0.0, 1.0),
                  child: Transform.scale(
                    scale: idScale,
                    child: identityColumn,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PickerBody extends StatelessWidget {
  const _PickerBody({
    required this.profiles,
    required this.selectingId,
    required this.focus,
    required this.manage,
    required this.onSelect,
    required this.onSelectAt,
    required this.onEdit,
    required this.onAdd,
  });

  final List<Profile> profiles;
  final int? selectingId;

  /// Linear 0→1 across the focus phase — dims the others and fades the copy.
  final double focus;
  final bool manage;
  final ValueChanged<Profile> onSelect;
  final ValueChanged<Offset> onSelectAt;
  final ValueChanged<Profile> onEdit;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final canAdd = profiles.length < kMaxProfiles;
    final selecting = selectingId != null;
    // The prompt copy fades as the focus phase begins so attention lands on the
    // chosen profile rather than the header.
    final copyOpacity = 1.0 - ProfileSelectCurves.copyFade.transform(focus);

    if (profiles.isEmpty) {
      return EmptyState(
        icon: Icons.group_add_outlined,
        message: 'Create your first profile',
        subtitle: 'Reading profiles keep progress, follows and a mood theme '
            'separate for everyone who shares this account.',
        action: PrimaryPillButton(
          label: 'Add profile',
          icon: Icons.add,
          onPressed: onAdd,
        ),
      );
    }

    final tiles = <Widget>[
      for (var i = 0; i < profiles.length; i++)
        _revealed(
          reduceMotion,
          i,
          _ProfileTile(
            profile: profiles[i],
            manage: manage,
            dimmed: selecting && selectingId != profiles[i].id,
            focused: selectingId == profiles[i].id,
            focus: focus,
            onTap: () => manage ? onEdit(profiles[i]) : onSelect(profiles[i]),
            onTapAt: onSelectAt,
            onLongPress: () => onEdit(profiles[i]),
          ),
        ),
      if (canAdd)
        _revealed(
          reduceMotion,
          profiles.length,
          _AddTile(
            dimmed: selecting,
            focus: focus,
            onTap: onAdd,
          ),
        ),
    ];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl4,
      ),
      child: Column(
        children: [
          Opacity(
            opacity: copyOpacity,
            child: Column(
              children: [
                const HeroHeading(
                  text: "Who's reading?",
                  fontSize: 44,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'What are you going to read today?',
                  textAlign: TextAlign.center,
                  style: AppTypography.h3.copyWith(color: AppColors.fg),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  manage
                      ? 'Tap a profile to edit it.'
                      : 'Choose a profile to continue.',
                  textAlign: TextAlign.center,
                  style: AppTypography.body.copyWith(color: AppColors.muted),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.xl3),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: AppSpacing.xl2,
            runSpacing: AppSpacing.xl2,
            children: tiles,
          ),
        ],
      ),
    );
  }

  /// Wrap a tile in the app's [ScrollReveal] entrance unless the platform asks
  /// for reduced motion, in which case it renders immediately.
  Widget _revealed(bool reduceMotion, int index, Widget child) {
    if (reduceMotion) return child;
    return ScrollReveal(index: index, child: child);
  }
}

class _ProfileTile extends StatelessWidget {
  const _ProfileTile({
    required this.profile,
    required this.manage,
    required this.dimmed,
    required this.focused,
    required this.focus,
    required this.onTap,
    required this.onTapAt,
    required this.onLongPress,
  });

  final Profile profile;
  final bool manage;
  final bool dimmed;
  final bool focused;

  /// Linear 0→1 across the focus phase.
  final double focus;
  final VoidCallback onTap;
  final ValueChanged<Offset> onTapAt;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    // Focus/select reads WARM: the chosen tile takes an amber avatar ring and
    // an amber glass-card border (replacing the old white/violet focus ring).
    final ring = focused
        ? AppColors.accentAmber
        : (profile.mood.isTinted
            ? Color.lerp(ProfileMoodColors.base, profile.mood.tint, 0.7)
            : null);

    // The focus phase drives three coupled moves off one fraction: the chosen
    // tile lifts with a gentle over-shoot and stays crisp, while the rest fall
    // back, dim and gaussian-blur into a soft depth-of-field.
    final dim = dimmed ? ProfileSelectCurves.focusFall.transform(focus) : 0.0;
    final opacity = lerpDouble(1.0, 0.12, dim)!;
    final blur = lerpDouble(0.0, 9.0, dim)!;
    final scale = focused
        ? lerpDouble(1.0, 1.18, ProfileSelectCurves.lift.transform(focus))!
        : lerpDouble(1.0, 0.9, dim)!;

    Widget tile = Semantics(
      label: profile.name,
      button: true,
      child: InkWell(
        onTap: onTap,
        onTapDown: (details) => onTapAt(details.globalPosition),
        onLongPress: onLongPress,
        borderRadius: BorderRadius.circular(AppRadius.xl),
        child: _GlassTileCard(
          focused: focused,
          child: SizedBox(
            width: 108,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Stack(
                  alignment: Alignment.center,
                  children: [
                    ProfileAvatar(
                      avatarKey: profile.avatarKey,
                      ringColor: ring,
                    ),
                    if (manage)
                      const DecoratedBox(
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: AppColors.scrim,
                        ),
                        child: SizedBox(
                          width: 96,
                          height: 96,
                          child: Center(
                            child: Icon(
                              Icons.edit_outlined,
                              color: Colors.white,
                              size: 28,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  profile.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: AppTypography.labelLg,
                ),
              ],
            ),
          ),
        ),
      ),
    );

    if (blur > 0.05) {
      tile = ImageFiltered(
        imageFilter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: tile,
      );
    }

    return Opacity(
      opacity: opacity,
      child: Transform.scale(scale: scale, child: tile),
    );
  }
}

class _AddTile extends StatelessWidget {
  const _AddTile({
    required this.dimmed,
    required this.focus,
    required this.onTap,
  });

  final bool dimmed;

  /// Linear 0→1 across the focus phase.
  final double focus;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final dim = dimmed ? ProfileSelectCurves.focusFall.transform(focus) : 0.0;
    return Opacity(
      opacity: lerpDouble(1.0, 0.3, dim)!,
      child: Semantics(
        label: 'Add profile',
        button: true,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadius.xl),
          child: _GlassTileCard(
            focused: false,
            child: SizedBox(
              width: 108,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 96,
                    height: 96,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.surface2.withAlpha(90),
                      border: Border.all(
                        color: AppColors.accentAmber.withValues(alpha: 0.35),
                        width: 2,
                      ),
                    ),
                    alignment: Alignment.center,
                    child: const Icon(
                      Icons.add,
                      color: AppColors.accentAmber,
                      size: 34,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'Add profile',
                    textAlign: TextAlign.center,
                    style: AppTypography.labelLg.copyWith(
                      color: AppColors.muted,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Frosted glass card that wraps a picker tile. Reads as a warm-dark glass
/// panel over the mood backdrop; the border warms to amber when the tile is
/// [focused] (mid-selection), replacing the old bare white/violet focus ring.
class _GlassTileCard extends StatelessWidget {
  const _GlassTileCard({required this.focused, required this.child});

  final bool focused;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppRadius.xl);
    return ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.lg,
          ),
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(
              alpha: focused ? 0.62 : 0.42,
            ),
            borderRadius: radius,
            border: Border.all(
              color: focused ? AppColors.accentAmber : AppColors.border,
              width: focused ? 1.5 : 1,
            ),
            boxShadow: focused
                ? [
                    BoxShadow(
                      color: AppColors.accentAmber.withValues(alpha: 0.22),
                      blurRadius: 24,
                      spreadRadius: -2,
                    ),
                  ]
                : null,
          ),
          child: child,
        ),
      ),
    );
  }
}
