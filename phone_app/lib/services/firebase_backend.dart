/// Wiring for the Firebase backend, during and after the GitHub cutover.
///
/// Split by what is safe to publish, because this repo is public:
///
/// * [kProject] holds the Web API key and database URL. Both are public
///   identifiers that already ship inside the APK; the security rules, not
///   their secrecy, are what protect the data.
/// * The account email and password are entered once per device and kept in
///   the OS keystore, next to the GitHub token this app already stores there.
///
/// Nothing here reads `~/.config/crdt-sync/` — that is the desktop/Python
/// half (`wake_alarm/_sync.py`). On Android there is no such file.
library;

import 'dart:developer';
import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:wake_alarm_sync/services/google_sign_in_backend.dart';

/// The shared `kuhy-syncs` project.
///
/// `databaseUrl` is the **regional** host. The plain `*.firebaseio.com` form
/// answers 404 with a `correctUrl` body rather than an obvious error, which
/// reads like an auth failure and wastes a debugging session.
const kProject = FirebaseProject(
  apiKey: 'AIzaSyCF_sA3xCMehAYXK8eND-rAygb9NXXW_8E',
  databaseUrl:
      'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
);

/// Same options the GitHub token uses: off Android's deprecated
/// `encryptedSharedPreferences` path, and libsecret on Linux.
const _secure = FlutterSecureStorage();

// Everything below reaches the OS keystore through a platform channel, which
// `flutter test` has no binding for. The logic these wrap (parsing, the
// public/private split, sign-in) lives in `crdt_sync` and is covered there at
// 100%; what is left here is the two-line adapter.
// coverage:ignore-start

/// The keystore-backed home for the Firebase refresh token.
SecureCredentialStore credentialStore() => SecureCredentialStore(
  read: (key) => _secure.read(key: key),
  write: (key, value) => _secure.write(key: key, value: value),
  delete: (key) => _secure.delete(key: key),
);

/// Reads the per-device account, or null when sync has not been set up.
Future<FirebaseAccount?> loadAccount() async {
  try {
    return FirebaseAccount.tryParse(
      await _secure.read(key: kFirebaseAccountKey),
    );
  } on Object {
    // No secret service available: behave as "not configured" rather than
    // crashing the settings screen.
    return null;
  }
}

/// Stores the per-device account. Keystore only — never prefs, never source.
Future<void> saveAccount(FirebaseAccount account) =>
    _secure.write(key: kFirebaseAccountKey, value: account.toJsonString());

/// Reads the account from the keystore only, with no wrapper fallback.
///
/// Callers reading back an account they just wrote use this rather than
/// [loadAccount]: a fallback would be wrong there, and on Android the
/// wrapper route resolves to `file:///` and throws instead of returning null.
Future<FirebaseAccount?> storedAccount() async =>
    FirebaseAccount.tryParse(await _secure.read(key: kFirebaseAccountKey));

/// Forgets the account and any cached session.
Future<void> clearAccount() async {
  await _secure.delete(key: kFirebaseAccountKey);
  await credentialStore().clear();
}

/// Returns a signed-in Firebase client, or null when not configured.
///
/// Signs in with the stored password only when there is no cached refresh
/// token, so the usual path costs no authentication round trip.
Future<FirebaseRestClient?> openFirebase() async {
  final account = await loadAccount();
  if (account == null) {
    // A stored refresh token IS a signed-in device, even with no account
    // marker beside it. Treating the marker as the source of truth is what
    // made a phone with a live session sync over GitHub and 401 forever --
    // the credential was in the keystore the whole time, unused.
    return _clientFromStoredSession();
  }
  try {
    return await firebaseClientFor(
      config: kProject.configFor(account.email),
      store: credentialStore(),
      password: account.password,
    );
  } on Object {
    // Unreachable keystore or a rejected sign-in must not fail the push: the
    // app keeps syncing over GitHub, exactly as before the cutover.
    // Broader than Exception because an uninitialised platform binding
    // raises a FlutterError, which is an Error.
    return null;
  }
}

/// Whether this device can actually authenticate against Firebase.
///
/// True when either half of the state is present: the account marker
/// [loadAccount] reads, or a stored refresh token. The token is the half that
/// matters -- it is what signs requests -- so reporting the marker alone calls
/// a working device "not connected", which is exactly how a phone that was in
/// fact syncing looked broken.
Future<bool> isFirebaseConfigured() async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (await auth.hasSession()) return true;
    // storedAccount, not loadAccount: on Android the latter falls back to the
    // desktop wrapper's /sync-account route, which resolves to file:/// and
    // throws "No host specified in URI" -- observed on the phone, where it
    // turned a successful sign-in into "Google sign-in failed".
    if (await storedAccount() == null) return false;
    // A marker with no session behind it cannot sign a single request. Drop
    // just the marker so the settings screen offers a sign-in instead of a
    // dead banner -- not clearAccount(), which also sets the opt-out flag and
    // would stop the desktop wrapper re-provisioning after the next sign-in.
    await _secure.delete(key: kFirebaseAccountKey);
    return false;
  } on Object catch (error, stackTrace) {
    log(
      'session probe failed; reporting this device as not configured',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return false;
  }
}

/// Signs in with Google alone, for a device that has no account stored yet.
///
/// The one-tap path: [openFirebase] needs an account in the keystore to know
/// which email to use, but a fresh install has none. The Google token carries
/// the identity, so nothing has to be typed.
///
/// Returns null when the user dismisses the picker; throws [FirebaseAuthError]
/// when Google succeeds but resolves to a uid the security rules do not pin —
/// that would authenticate fine and then be denied every read and write, with
/// no other symptom.
Future<FirebaseRestClient?> openFirebaseWithGoogle({
  Future<String?> Function()? tokenFetcher,
  Future<void> Function(FirebaseAccount)? accountSaver,
  http.Client? httpClient,
}) async {
  final token = await (tokenFetcher ?? googleIdToken)();
  if (token == null) return null;
  final auth = FirebaseTokenProvider(
    apiKey: kProject.apiKey,
    store: credentialStore(),
    httpClient: httpClient,
  );
  final email = await auth.signInWithGoogle(
    idToken: token,
    expectedUid: kSyncUid,
  );
  // Saved unconditionally, and deliberately not gated on `email`:
  // `signInWithIdp` omits that field whenever the Google account hides it, and
  // gating the write on it returns a working client while persisting nothing,
  // so the next launch looks unconfigured and falls back to GitHub-only.
  // The session is already durable here — signInWithGoogle stored the refresh
  // token — and that token, not the address, is the credential.
  await (accountSaver ?? saveAccount)(
    FirebaseAccount(email: email ?? '', password: ''),
  );
  return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
}

/// Returns a client built from the keystore's refresh token alone, or null.
///
/// The recovery path for a device that has a live session but no account
/// marker -- the state a Google sign-in used to leave behind. Costs one
/// keystore read and no network round trip when there is no session, so it is
/// safe on the background-tick path [openFirebase] also serves.
Future<FirebaseRestClient?> _clientFromStoredSession() async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: kProject.apiKey,
      store: credentialStore(),
    );
    if (!await auth.hasSession()) return null;
    return FirebaseRestClient(databaseUrl: kProject.databaseUrl, auth: auth);
  } on Object catch (error, stackTrace) {
    log(
      'stored-session recovery failed; falling back to the GitHub mirror',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
}

// coverage:ignore-end

/// Wraps [github] so Firebase is primary and GitHub is kept as a mirror.
///
/// Returns [github] unchanged when this device has not been set up for
/// Firebase — a normal state during the cutover, not an error, and also the
/// rollback. The PC reads whichever backend answers first
/// (`_fetch_firebase_alarm() or _fetch_github_alarm()`), so a phone that has
/// not moved yet still reaches it.
Future<RemoteStore> syncBackend(RemoteStore github) async {
  final firebase = await openFirebase();
  return firebase == null
      ? github
      : MirrorStore(primary: firebase, mirror: github);
}
