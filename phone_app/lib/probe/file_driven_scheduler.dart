import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';

/// An [AlarmScheduler] whose sensors and NFC are files adb can write.
///
/// The emulator has no NFC and no step sensor, so the real dismiss sequence
/// and the whole morning session are unreachable on it. This bridge keeps
/// every alarm, ring and re-ring call on the real channel and replaces only
/// the three inputs hardware would supply:
///
/// - `files/tag`     — a tag id; consumed once, delivered to the NFC listener
/// - `files/steps`   — the step count the ring's walk stage reads
/// - `files/idle_ms` — how long the phone has "lain still"
///
/// under `/sdcard/Android/data/<package>/files/`. Probe-only: `lib/main.dart`
/// never constructs it.
class FileDrivenScheduler extends AlarmScheduler {
  /// Creates the bridge; starts polling on the first NFC registration.
  FileDrivenScheduler();

  static const Duration _poll = Duration(milliseconds: 500);

  Directory? _dir;
  Timer? _timer;
  void Function(String tagId)? _onTag;

  Future<Directory> _files() async =>
      _dir ??= (await getExternalStorageDirectory())!;

  Future<String?> _read(String name) async {
    final file = File(p.join((await _files()).path, name));
    if (!file.existsSync()) return null;
    return (await file.readAsString()).trim();
  }

  @override
  Future<bool> hasNfc() async => true;

  @override
  void onNfcTag(void Function(String tagId) onTag) {
    _onTag = onTag;
    _timer ??= Timer.periodic(_poll, (_) => unawaited(_deliverTag()));
  }

  /// Stops this instance's polling; another instance's listener is its own.
  @override
  void clearNfcListener() {
    _onTag = null;
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _deliverTag() async {
    final file = File(p.join((await _files()).path, 'tag'));
    if (!file.existsSync()) return;
    final id = (await file.readAsString()).trim();
    await file.delete();
    debugPrint('FileDrivenScheduler: tag $id');
    _onTag?.call(id);
  }

  @override
  Future<int> stepsSinceRingStart() async =>
      int.tryParse(await _read('steps') ?? '') ?? -1;

  @override
  Future<Duration?> motionIdle() async {
    final ms = int.tryParse(await _read('idle_ms') ?? '');
    return ms == null ? null : Duration(milliseconds: ms);
  }
}
