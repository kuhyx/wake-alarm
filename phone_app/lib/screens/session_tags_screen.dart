import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';
import 'package:wake_alarm_sync/ui/cues.dart';
import 'package:wake_alarm_sync/ui/dashed_slot.dart';

/// Registers the three NFC tags the morning session walks through.
///
/// Any slot may be left empty — its leg is then skipped — but the three must
/// be distinct from each other: one tag in two rooms is no walk at all. A
/// slot may reuse a *ring* tag; the bathroom tag is often ring tag 2.
class SessionTagsScreen extends StatefulWidget {
  /// Creates the screen; [scheduler] is injectable for tests.
  const SessionTagsScreen({super.key, this.scheduler});

  /// Platform bridge used to drive NFC reader mode.
  final AlarmScheduler? scheduler;

  @override
  State<SessionTagsScreen> createState() => _SessionTagsScreenState();
}

class _SessionTagsScreenState extends State<SessionTagsScreen> {
  late final AlarmScheduler _scheduler = widget.scheduler ?? AlarmScheduler();

  SessionTagSettings _settings = const SessionTagSettings();
  SessionTagSlot? _scanning;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    if (_scanning != null) unawaited(_scheduler.stopTagRegistration());
    _scheduler.clearNfcListener();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await SessionTagSettings.load();
    if (!mounted) return;
    setState(() => _settings = settings);
  }

  Future<void> _startScan(SessionTagSlot slot) async {
    _scheduler.onNfcTag((tagId) => unawaited(_onTag(slot, tagId)));
    final started = await _scheduler.startTagRegistration();
    if (!mounted) return;
    setState(() {
      _scanning = started ? slot : null;
      _status = started
          ? 'Tap the ${slot.name} tag against the phone…'
          : 'NFC is unavailable or switched off.';
    });
  }

  Future<void> _onTag(SessionTagSlot slot, String tagId) async {
    final taken = _settings.slotOf(tagId);
    await _scheduler.stopTagRegistration();
    if (taken != null && taken != slot) {
      if (!mounted) return;
      setState(() {
        _scanning = null;
        _status =
            'That is already the ${taken.name} tag. Use a different '
            'tag, in a different room.';
      });
      return;
    }
    await SessionTagSettings.saveTagAt(slot, tagId);
    final settings = await SessionTagSettings.load();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _scanning = null;
      _status = 'The ${slot.name} tag is registered.';
    });
  }

  IconData _iconForSlot(SessionTagSlot slot) => switch (slot) {
    SessionTagSlot.bathroom => Icons.shower,
    SessionTagSlot.wardrobe => Icons.checkroom,
    SessionTagSlot.desk => Icons.desk,
  };

  String _semanticLabelForSlot(SessionTagSlot slot) => switch (slot) {
    SessionTagSlot.bathroom => 'Bathroom (scale + shower)',
    SessionTagSlot.wardrobe => 'Wardrobe',
    SessionTagSlot.desk => 'Desk',
  };

  Widget _slotRow(SessionTagSlot slot) {
    final id = _settings.tagAt(slot);
    final scanning = _scanning == slot;
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Row(
        children: <Widget>[
          Icon(_iconForSlot(slot), semanticLabel: _semanticLabelForSlot(slot)),
          const SizedBox(width: 12),
          Expanded(
            child: id != null
                ? KeyedSubtree(
                    key: ValueKey<String>('content:tag-${slot.name}'),
                    child: Text(id),
                  )
                : const DashedSlot(),
          ),
          const SizedBox(width: 12),
          FilledButton(
            key: ValueKey<String>('register-${slot.name}'),
            onPressed: _scanning != null ? null : () => _startScan(slot),
            child: scanning
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    id == null ? Icons.add : Icons.refresh,
                    semanticLabel: id == null
                        ? 'Register ${slot.name} tag'
                        : 'Register ${slot.name} tag again',
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
            for (final slot in SessionTagSlot.values) _slotRow(slot),
            StatusCue(semanticLabel: _status),
          ],
        ),
      ),
    );
  }
}
