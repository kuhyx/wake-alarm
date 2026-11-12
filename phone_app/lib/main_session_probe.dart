import 'package:material_ui/material_ui.dart';

import 'package:wake_alarm_sync/main.dart';
import 'package:wake_alarm_sync/probe/file_driven_scheduler.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

/// Emulator entrypoint: the whole morning, driven from adb.
///
/// Like `main_ring_probe.dart` it rings on launch -- unless the morning is
/// already live, in which case the launch is redirected into it exactly as
/// the launcher's would be -- but it runs the app on a [FileDrivenScheduler]
/// and registers fixed tag ids, so the dismiss walk and the session legs can
/// be fed by writing files:
///
/// ```sh
/// F=/sdcard/Android/data/com.kuhy.wake_alarm_sync/files
/// adb shell "echo -n ring1 > $F/tag"; adb shell "echo 30 > $F/steps"
/// adb shell "echo -n ring2 > $F/tag"   # then answer three questions
/// adb shell "echo -n bath > $F/tag"    # ... bath, ward, desk
/// ```
///
/// Not part of the shipped app: `flutter build apk` uses `lib/main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await RoomProofSettings.saveNfcTagAt(0, 'ring1');
  await RoomProofSettings.saveNfcTagAt(1, 'ring2');
  await SessionTagSettings.saveTagAt(SessionTagSlot.bathroom, 'bath');
  await SessionTagSettings.saveTagAt(SessionTagSlot.wardrobe, 'ward');
  await SessionTagSettings.saveTagAt(SessionTagSlot.desk, 'desk');
  final scheduler = AlarmScheduler();
  if (!await scheduler.morningLive()) await scheduler.ringNow();
  runApp(const WakeAlarmSyncApp(newScheduler: FileDrivenScheduler.new));
}
