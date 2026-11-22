/// A debug-only sync backend: the Firebase RTDB emulator on the PC.
///
/// The emulator checks (a bypass reaching "the test backend") need a
/// backend, and the AVD must never sign in to prod: a probe's per-date
/// merge would overwrite the phone's real morning. So the probe build
/// passes `--dart-define=WAKE_SYNC_EMULATOR=http://10.0.2.2:9000` (the AVD's
/// name for the PC's loopback), and every sync open then returns this client
/// *instead of* prod Firebase and the GitHub mirror, never beside them.
///
/// The define is a compile-time constant: release and `deploy.sh` builds
/// never set it, so there the branch is dead code. The emulator answers
/// `auth=owner` as admin, so no Google sign-in is involved.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;

/// The emulator's origin, or empty (every release build).
const String kSyncEmulatorUrl = String.fromEnvironment('WAKE_SYNC_EMULATOR');

/// Whether this build syncs to the emulator only.
bool get syncEmulatorOn => kSyncEmulatorUrl.isNotEmpty;

/// The account marker the sync gates look for; carries no credential.
const FirebaseAccount emulatorAccount = FirebaseAccount(
  email: 'emulator',
  password: '',
);

/// Signs every request `auth=owner`, the emulator's admin token.
class EmulatorTokenProvider extends FirebaseTokenProvider {
  /// Creates a provider that never talks to Google.
  EmulatorTokenProvider()
    : super(apiKey: 'emulator', store: InMemoryCredentialStore());

  @override
  Future<String> idToken() async => 'owner';

  @override
  Future<bool> hasSession() async => true;
}

/// A client for the emulator at [url].
FirebaseRestClient emulatorClient({
  String url = kSyncEmulatorUrl,
  http.Client? httpClient,
}) => FirebaseRestClient(
  databaseUrl: url,
  auth: EmulatorTokenProvider(),
  httpClient: httpClient,
);
