import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/today_stakes.dart';
import 'package:wake_alarm_sync/ui/spoken_label.dart';
import 'package:wake_alarm_sync/ui/theme.dart';

/// The stakes of [view] as glyph rows: times and dates are the only
/// characters painted; each row speaks its sentence from [StakesView].
class StakesMarks extends StatelessWidget {
  /// Creates the rows for [view].
  const StakesMarks({required this.view, super.key});

  /// The stakes to draw.
  final StakesView view;

  static String _dm(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}.'
      '${d.month.toString().padLeft(2, '0')}';

  static String _hm(int h, int m) =>
      '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final warning =
        theme.extension<AppStatusColors>()?.warning ?? theme.colorScheme.error;
    final kindIcon = switch (view.kind) {
      StakesDayKind.free => Icons.event_available,
      StakesDayKind.sick => Icons.sick_outlined,
      StakesDayKind.stick => Icons.gavel_outlined,
      StakesDayKind.carrot => Icons.emoji_events_outlined,
    };
    final rows = <Widget>[
      _row('title', view.title, <Widget>[
        Icon(kindIcon, color: theme.colorScheme.primary),
        Icon(view.isToday ? Icons.today : Icons.event, size: 18),
        Text(_dm(view.day), style: theme.textTheme.titleMedium),
      ]),
    ];
    final words = view.stakes;
    final dismissBy = view.dismissBy;
    final lock = view.lockThrough;
    final finishBy = view.finishBy;
    final open = view.pcOpenUntil;
    final ring = view.pcRingAt;
    if (dismissBy != null && lock != null) {
      rows.add(
        _row('stick', words.first, <Widget>[
          const Icon(Icons.alarm),
          Text(hhmm(dismissBy)),
          const Icon(Icons.arrow_forward, size: 16),
          const Icon(Icons.lock_outline),
          Text(_dm(lock)),
        ]),
      );
    } else if (finishBy != null && open != null) {
      rows.add(
        _row('carrot', words.first, <Widget>[
          const Icon(Icons.flag_outlined),
          Text(hhmm(finishBy)),
          const Icon(Icons.arrow_forward, size: 16),
          const Icon(Icons.computer),
          Text(_hm(open.hour, open.minute)),
        ]),
      );
    } else if (view.kind != StakesDayKind.free &&
        view.kind != StakesDayKind.sick) {
      rows.add(
        _row('unarmed', words.first, const <Widget>[Icon(Icons.alarm_off)]),
      );
    }
    if (ring != null) {
      rows.add(
        _row('pc-ring', words.last, <Widget>[
          const Icon(Icons.computer),
          const Icon(Icons.notifications_active_outlined),
          Text(hhmm(ring)),
        ]),
      );
    }
    rows
      ..addAll(_pending(warning))
      ..add(
        _row('streak', view.streak, <Widget>[
          Icon(
            Icons.local_fire_department_outlined,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          Text('${view.streakCount}'),
        ]),
      );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: rows,
    );
  }

  /// The rows for what is already in force, in `view.pending`'s order.
  List<Widget> _pending(Color warning) {
    final spoken = view.pending.iterator;
    String next() => spoken.moveNext() ? spoken.current : '';
    final locked = view.lockedThrough;
    final style = TextStyle(color: warning);
    return <Widget>[
      if (view.escapedToday)
        _row('escaped', next(), <Widget>[
          Icon(Icons.bug_report_outlined, color: warning),
          Icon(Icons.check, color: warning),
        ]),
      if (locked != null)
        _row('locked', next(), <Widget>[
          Icon(Icons.lock_outline, color: warning),
          Text(_dm(locked), style: style),
        ]),
      if (view.missedToday)
        _row('missed', next(), <Widget>[
          Icon(Icons.close, color: warning),
          Icon(Icons.computer, color: warning),
        ]),
    ];
  }

  static Widget _row(String what, String words, List<Widget> marks) => Padding(
    key: ValueKey<String>('stakes-$what'),
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: SpokenLabel(
      semanticLabel: words,
      child: Row(
        children: <Widget>[
          for (final mark in marks) ...<Widget>[mark, const SizedBox(width: 8)],
        ],
      ),
    ),
  );
}
