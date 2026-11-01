import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:wake_alarm_sync/services/ramp_progress.dart';

/// One crdt log the export covers.
typedef LogSlot = ({
  Log Function() snapshot,
  Future<void> Function(Log merged) replaceAll,
});

/// Marks the file as this app's export.
const exportFormat = 'wake_alarm_export';

/// Shape version.
const exportVersion = 1;

/// Every slot's log plus the ramp dates as JSON; no device id or secrets.
Future<String> buildExport(Map<String, LogSlot> slots, {DateTime? now}) async {
  final dates = (await RampProgress.load()).toList()..sort();
  return const JsonEncoder.withIndent('  ').convert(
    buildEnvelope(
      format: exportFormat,
      version: exportVersion,
      now: now ?? DateTime.now(),
      body: <String, Object?>{
        'logs': <String, Object?>{
          for (final entry in slots.entries)
            entry.key: jsonDecode(logToJson(entry.value.snapshot())),
        },
        'ramp_earned_dates': dates,
      },
    ),
  );
}

/// Merges via [mergeLogs] only, after validating all; throws [FormatException].
Future<void> importExport(String text, Map<String, LogSlot> slots) async {
  final parsed = _parse(text);
  for (final entry in parsed.logs.entries) {
    final slot = slots[entry.key];
    if (slot == null) continue;
    await slot.replaceAll(mergeLogs(slot.snapshot(), entry.value));
  }
  await RampProgress.merge(parsed.rampDates);
}

typedef _Parsed = ({Map<String, Log> logs, List<String> rampDates});

_Parsed _parse(String text) {
  final decoded = parseEnvelope(
    text,
    format: exportFormat,
    version: exportVersion,
  );
  final rawLogs = decoded['logs'];
  if (rawLogs is! Map<String, dynamic>) {
    throw const FormatException('export has no "logs" object');
  }
  final logs = <String, Log>{};
  for (final entry in rawLogs.entries) {
    try {
      logs[entry.key] = logFromJson(jsonEncode(entry.value));
    } on Object catch (error) {
      throw FormatException('log "${entry.key}" is malformed ($error)');
    }
  }
  final rawDates = decoded['ramp_earned_dates'];
  final dates = rawDates is List ? rawDates.whereType<String>() : <String>[];
  return (logs: logs, rampDates: dates.toList());
}
