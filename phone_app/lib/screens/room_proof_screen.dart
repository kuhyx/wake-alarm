import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

/// Registers the two NFC tags the dismiss sequence walks between.
///
/// Both slots must hold **different** tags. With fewer than two distinct tags
/// the tag stages are unsatisfiable, so the ring screen falls straight through
/// to the bypass — a weaker morning, not a locked-out one.
class RoomProofScreen extends StatefulWidget {
  /// Creates the screen; [scheduler] is injectable for tests.
  const RoomProofScreen({super.key, this.scheduler});

  /// Platform bridge used to drive NFC reader mode.
  final AlarmScheduler? scheduler;

  @override
  State<RoomProofScreen> createState() => _RoomProofScreenState();
}

class _RoomProofScreenState extends State<RoomProofScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();

  RoomProofSettings _settings = const RoomProofSettings();
  int? _scanningSlot;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    if (_scanningSlot != null) unawaited(_scheduler.stopTagRegistration());
    _scheduler.clearNfcListener();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await RoomProofSettings.load();
    if (!mounted) return;
    var status = '';
    for (var i = 0; i < RoomProofSettings.requiredTagCount; i++) {
      if (settings.tagAt(i) != null) {
        status = 'Tag ${i + 1} registered.';
        break;
      }
    }
    setState(() {
      _settings = settings;
      _status = status;
    });
  }

  Future<void> _startScan(int slot) async {
    _scheduler.onNfcTag((tagId) => unawaited(_onTag(slot, tagId)));
    final started = await _scheduler.startTagRegistration();
    if (!mounted) return;
    setState(() {
      _scanningSlot = started ? slot : null;
      _status = started
          ? 'Tap tag ${slot + 1} against the phone…'
          : 'NFC is unavailable or switched off.';
    });
  }

  Future<void> _onTag(int slot, String tagId) async {
    // The same tag in both slots would let one tap satisfy both stages, which
    // removes the walk between them — the entire point of having two.
    final other = _settings.tagAt(slot == 0 ? 1 : 0);
    if (tagId == other) {
      await _scheduler.stopTagRegistration();
      if (!mounted) return;
      setState(() {
        _scanningSlot = null;
        _status =
            'That is already tag ${slot == 0 ? 2 : 1}. Use a different '
            'tag, in a different room.';
      });
      return;
    }
    await RoomProofSettings.saveNfcTagAt(slot, tagId);
    final settings = await RoomProofSettings.load();
    await _scheduler.stopTagRegistration();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _scanningSlot = null;
      _status = 'Tag ${slot + 1} registered.';
    });
  }

  Widget _slotRow(int slot) {
    final id = _settings.tagAt(slot);
    final scanning = _scanningSlot == slot;
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Row(
        children: <Widget>[
          CircleAvatar(radius: 14, child: Text('${slot + 1}')),
          const SizedBox(width: 12),
          Expanded(
            child: id != null
                ? KeyedSubtree(
                    key: ValueKey<String>('content:tag-$slot'),
                    child: Text(id),
                  )
                : const DashedSlot(),
          ),
          const SizedBox(width: 12),
          FilledButton(
            key: ValueKey<String>('register-$slot'),
            onPressed: _scanningSlot != null ? null : () => _startScan(slot),
            child: scanning
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    id == null ? Icons.add : Icons.refresh,
                    semanticLabel: id == null
                        ? 'Register tag ${slot + 1}'
                        : 'Register tag ${slot + 1} again',
                  ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            for (var i = 0; i < RoomProofSettings.requiredTagCount; i++)
              _slotRow(i),
            StatusCue(semanticLabel: _status),
          ],
        ),
      ),
    );
  }
}
