/// Shared end-to-end encryption plumbing for the sync tests.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:wake_alarm_sync/services/alarm_sync_e2e.dart';

import 'fake_secure_storage.dart';

/// The passphrase every test device shares.
const testPassphrase = 'test-passphrase';

/// A keystore holding [testPassphrase], cheap Argon2id, a fresh copy memo.
void installE2eTestStorage({Map<String, String>? initial}) {
  e2eArgon2Params = const Argon2Params(
    memoryKiB: 8,
    iterations: 1,
    parallelism: 1,
  );
  resetE2eCopyMemo();
  installFakeSecureStorage(
    initial: {'crdt_sync_e2e_passphrase': testPassphrase, ...?initial},
  );
}

/// A GitHub Contents API stand-in that stores what is PUT and lists
/// directories from it, so the encryption header reads back.
class MemGitHub {
  /// Starts holding [files] (repo path -> text).
  MemGitHub([Map<String, String>? files]) : files = {...?files};

  /// Repo path -> text.
  final Map<String, String> files;

  /// Every PUT path, in order.
  final List<String> putPaths = [];

  /// The mock HTTP client.
  late final http.Client httpClient = http_testing.MockClient(_handle);

  /// A [GitHubClient] over [httpClient].
  GitHubClient client() =>
      GitHubClient(owner: 'o', repo: 'r', token: 't', httpClient: httpClient);

  /// The decrypted text at [path], read like another device would.
  Future<String?> opened(String path) async {
    final state = await openEncryptedStore(
      store: client(),
      oldPrefix: legacyAlarmPrefix,
      readPassphrase: () async => testPassphrase,
    );
    return await (state as E2eReady).store.getFileText(path);
  }

  Future<http.Response> _handle(http.Request request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) return http.Response('{}', 200);
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      files[key] = utf8.decode(base64.decode(body['content'] as String));
      putPaths.add(key);
      return http.Response('{}', 200);
    }
    final text = files[key];
    if (text != null) {
      return http.Response(
        jsonEncode({'content': base64.encode(utf8.encode(text)), 'sha': 's'}),
        200,
      );
    }
    final names = {
      for (final k in files.keys)
        if (k.startsWith('$key/')) k.substring(key.length + 1).split('/')[0],
    };
    if (names.isEmpty) return http.Response('{}', 404);
    return http.Response(
      jsonEncode([
        for (final n in names)
          {
            'type': files.containsKey('$key/$n') ? 'file' : 'dir',
            'name': n,
            'path': '$key/$n',
          },
      ]),
      200,
    );
  }
}
