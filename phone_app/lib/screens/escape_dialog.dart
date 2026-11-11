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
    const reasonWords = 'What went wrong?';
    return AlertDialog(
      // The keyboard covers half a small screen; scroll instead of overflow.
      scrollable: true,
      icon: const Icon(
        Icons.bug_report_outlined,
        semanticLabel: 'That was a bug',
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          MergeSemantics(
            child: Semantics(
              label: reasonWords,
              child: TextField(
                controller: _reason,
                autofocus: true,
                maxLines: 4,
                minLines: 2,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.edit_note),
                  border: OutlineInputBorder(),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: <Widget>[
              Expanded(
                child: LinearProgressIndicator(
                  value: (_length / escapeReasonMinChars)
                      .clamp(0, 1)
                      .toDouble(),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '$_length/$escapeReasonMinChars',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ],
      ),
      actions: <Widget>[
        IconButton(
          key: const Key('escape-cancel'),
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.close, semanticLabel: 'Cancel'),
        ),
        FilledButton(
          key: const Key('escape-confirm'),
          onPressed: ready
              ? () => Navigator.of(context).pop(_reason.text.trim())
              : null,
          child: const Icon(Icons.check, semanticLabel: 'Excuse this morning'),
        ),
      ],
    );
  }
}
