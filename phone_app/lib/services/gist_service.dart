import 'dart:convert';

import 'package:http/http.dart' as http;

const _gistFileName = 'wake_alarm_sync.json';

/// Reads the current alarm time from the Gist.
///
/// Returns null if the Gist is not yet configured or the request fails.
Future<({int hour, int minute})?> readGistAlarm({
  required String token,
  required String gistId,
}) async {
  final uri = Uri.parse('https://api.github.com/gists/$gistId');
  final response = await http.get(
    uri,
    headers: {'Authorization': 'Bearer $token'},
  );
  if (response.statusCode != 200) return null;

  final body = jsonDecode(response.body) as Map<String, dynamic>;
  final files = body['files'] as Map<String, dynamic>?;
  final fileEntry = files?[_gistFileName] as Map<String, dynamic>?;
  final fileContent = fileEntry?['content'] as String?;
  if (fileContent == null) return null;

  final data = jsonDecode(fileContent) as Map<String, dynamic>;
  final hour = data['alarm_hour'] as int?;
  final minute = data['alarm_minute'] as int?;
  if (hour == null || minute == null) return null;
  return (hour: hour, minute: minute);
}

/// Writes the chosen alarm time to the Gist, creating the file if absent.
Future<void> writeGistAlarm({
  required String token,
  required String gistId,
  required int hour,
  required int minute,
}) async {
  final content = jsonEncode({'alarm_hour': hour, 'alarm_minute': minute});
  final uri = Uri.parse('https://api.github.com/gists/$gistId');
  final response = await http.patch(
    uri,
    headers: {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    },
    body: jsonEncode({
      'files': {
        _gistFileName: {'content': content},
      },
    }),
  );
  if (response.statusCode != 200) {
    throw Exception(
      'Gist write failed: HTTP ${response.statusCode}',
    );
  }
}

/// Creates a new private Gist and returns its ID.
Future<String> createGist({required String token}) async {
  final content = jsonEncode({'alarm_hour': 7, 'alarm_minute': 0});
  final uri = Uri.parse('https://api.github.com/gists');
  final response = await http.post(
    uri,
    headers: {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    },
    body: jsonEncode({
      'description': 'wake_alarm PC sync',
      'public': false,
      'files': {
        _gistFileName: {'content': content},
      },
    }),
  );
  if (response.statusCode != 201) {
    throw Exception(
      'Gist create failed: HTTP ${response.statusCode}',
    );
  }
  final body = jsonDecode(response.body) as Map<String, dynamic>;
  return body['id'] as String;
}
