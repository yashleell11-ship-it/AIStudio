/// Named routes for the reading-profiles feature. Kept in the feature (rather
/// than the shared `Routes` table) so the profiles surface owns its own deep
/// links. Registered in `app/router/app_router.dart`.
abstract final class ProfileRoutes {
  /// The Netflix-style picker + management surface.
  static const String picker = '/profiles';

  /// Full-screen "Add profile" form.
  static const String create = '/profiles/create';

  /// go_router path pattern for the edit form (`:id` path parameter).
  static const String editPattern = '/profiles/edit/:id';

  /// Concrete edit path for [id].
  static String edit(int id) => '/profiles/edit/$id';
}
