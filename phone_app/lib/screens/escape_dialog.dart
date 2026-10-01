import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/stakes.dart';

/// Asks why this morning should be excused; the reason, or null if
/// cancelled.
///
/// The confirm button stays disabled until the reason has at least
/// [escapeReasonMinChars] characters: the hatch exists for bugs, and a typed
/// explanation is what the incident report is read against.
Future<String?> showEscapeDialog(BuildContext context) =>
    showDialog<String>(context: context, builder: (_) => const EscapeDialog());

/// The escape-hatch dialog; see [showEscapeDialog].
class EscapeDialog extends StatefulWidget {
  /// Creates the dialog.
  const EscapeDialog({super.key});

  @override
  State<EscapeDialog> createState() => _EscapeDialogState();
}

class _EscapeDialogState extends State<EscapeDialog> {
  final TextEditingController _reason = TextEditingController();

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  int get _length => _reason.text.trim().length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ready = _length >= escapeReasonMinChars;
    return AlertDialog(
      // The keyboard covers half a small screen; scroll instead of overflow.
      scrollable: true,
      title: const Text('That was a bug'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const Text(
            'Lifts the app lockdown, clears the streak, cancels today’s PC '
            'penalty and stops a ringing PC. Every use is listed in the '
            'incident report.',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _reason,
            autofocus: true,
            maxLines: 4,
            minLines: 2,
            decoration: const InputDecoration(
              labelText: 'What went wrong?',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          Text(
            '$_length / $escapeReasonMinChars characters',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: ready
              ? () => Navigator.of(context).pop(_reason.text.trim())
              : null,
          child: const Text('Excuse this morning'),
        ),
      ],
    );
  }
}
