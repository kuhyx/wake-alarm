import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/alarm_scheduler.dart';
import 'package:wake_alarm_sync/services/room_proof_settings.dart';

/// Registers the separate-room proofs: the NFC tag and the printed QR code.
///
/// Without a registered tag, NFC can never satisfy the room proof and the
/// steps fallback becomes the only way to dismiss — which is exactly the
/// single-mechanism dependency the redundancy exists to avoid.
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
  final TextEditingController _qr = TextEditingController();

  String? _tagId;
  bool _scanning = false;
  String _status = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    if (_scanning) unawaited(_scheduler.stopTagRegistration());
    _scheduler.clearNfcListener();
    _qr.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final settings = await RoomProofSettings.load();
    if (!mounted) return;
    setState(() {
      _tagId = settings.nfcTagId;
      _qr.text = settings.qrPayload ?? '';
    });
  }

  Future<void> _startScan() async {
    _scheduler.onNfcTag(_onTag);
    final started = await _scheduler.startTagRegistration();
    if (!mounted) return;
    setState(() {
      _scanning = started;
      _status = started
          ? 'Tap the tag against the phone…'
          : 'NFC is unavailable or switched off.';
    });
  }

  Future<void> _onTag(String tagId) async {
    await RoomProofSettings.saveNfcTag(tagId);
    await _scheduler.stopTagRegistration();
    if (!mounted) return;
    setState(() {
      _tagId = tagId;
      _scanning = false;
      _status = 'Tag registered.';
    });
  }

  Future<void> _saveQr() async {
    await RoomProofSettings.saveQrPayload(_qr.text.trim());
    if (!mounted) return;
    setState(() => _status = 'QR code saved.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Room proof')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('NFC tag: ${_tagId ?? "none registered"}'),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _scanning ? null : _startScan,
              child: Text(_scanning ? 'Waiting for tag…' : 'Register NFC tag'),
            ),
            const SizedBox(height: 32),
            TextField(
              controller: _qr,
              decoration: const InputDecoration(
                labelText: 'QR code text',
                helperText: 'Text encoded in the code printed for that room',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(onPressed: _saveQr, child: const Text('Save QR code')),
            const SizedBox(height: 24),
            Text(_status),
          ],
        ),
      ),
    );
  }
}

/// Local helper so this file need not import dart:async for fire-and-forget.
void unawaited(Future<void> future) {}
