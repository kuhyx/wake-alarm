import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:wake_alarm_sync/services/alarm_sync_service.dart';
import 'package:wake_alarm_sync/services/data_export.dart';
import 'package:wake_alarm_sync/services/free_day_pool.dart';
import 'package:wake_alarm_sync/services/sick_day_pool.dart';

/// The three logs; pass the live [alarm] so no stale twin overwrites it.
Future<Map<String, LogSlot>> openLogSlots({AlarmSyncService? alarm}) async {
  final alarmStore = alarm ?? await AlarmSyncService.open();
  final free = await FreeDayPool.open();
  final sick = await SickDayPool.open();
  return {
    'alarm': (snapshot: alarmStore.snapshot, replaceAll: alarmStore.replaceAll),
    'free_days': (snapshot: free.snapshot, replaceAll: free.replaceAll),
    'sick_days': (snapshot: sick.snapshot, replaceAll: sick.replaceAll),
  };
}

/// Saves the export to device storage via the system Save-as picker.
///
/// False when the picker was cancelled.
Future<bool> saveExport({AlarmSyncService? alarm}) async {
  final now = DateTime.now();
  final json = await buildExport(await openLogSlots(alarm: alarm), now: now);
  final day = now.toIso8601String().substring(0, 10);
  return await exportJsonText(
    fileName: 'wake-alarm-export-$day.json',
    text: json,
  );
}

/// Picks an export and merges it; false when the picker was cancelled.
Future<bool> pickAndImport({AlarmSyncService? alarm}) async {
  final text = await pickJsonText();
  if (text == null) return false;
  await importExport(text, await openLogSlots(alarm: alarm));
  return true;
}
