/// Percent-encode an opaque connector key (series key / chapter key) for use
/// as a URL path segment.
///
/// Connector keys are opaque strings that may contain `/` or other
/// percent-worthy characters (see `docs/CLAUDE_HANDOFF.md` §2 and the mobile
/// migration spec). The backend's `:path` route converters expect the
/// slash-separated form to survive: split on `/`, percent-encode each
/// sub-segment, and rejoin with a raw `/` — mirrors the web client's
/// `encodePathKey` in `frontend/src/services/http.ts`.
///
/// Never parse or otherwise interpret the key itself — this only escapes it
/// for transport.
String encodePathKey(String key) =>
    key.split('/').map(Uri.encodeComponent).join('/');
