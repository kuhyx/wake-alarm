import 'package:material_ui/material_ui.dart';
import 'package:wake_alarm_sync/services/morning_session.dart';
import 'package:wake_alarm_sync/services/session_rules.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

/// What a check-in attempt came to: the status line, and whether it stuck.
typedef CheckInResult = ({String detail, bool recorded});

/// The weigh-in field's state and the energy tap, kept out of the screen.
///
/// Holds what used to be four fields on `_SessionScreenState`: the text
/// controller, the last weight (for the jump check), the value awaiting a
/// retyped confirmation, and now the energy level. [submit] applies the
/// rules in order — energy first, since it is the cheaper thing to fix —
/// and only touches the session when everything passed.
class SessionCheckIn {
  /// The weight field's controller; disposed by [dispose].
  final TextEditingController input = TextEditingController();

  /// The previous morning's weight, for the plausibility jump check.
  double? lastWeight;

  /// A weight awaiting a retyped confirmation, if the jump was large.
  double? confirming;

  /// The tapped energy level, or null.
  int? energy;

  /// Validates and, if everything passes, records the check-in on [session].
  CheckInResult submit(MorningSession session, DateTime now) {
    final level = energy;
    if (level == null) {
      return (
        detail: 'Tap your energy ($minEnergy-$maxEnergy) first',
        recorded: false,
      );
    }
    final check = checkWeight(
      input.text,
      last: lastWeight,
      confirming: confirming,
    );
    if (!check.accepted) {
      confirming = check.verdict == WeightVerdict.needsConfirm
          ? check.kg
          : null;
      return (detail: check.detail, recorded: false);
    }
    confirming = null;
    input.clear();
    return (
      detail: session.enterCheckIn(check.kg!, level, now),
      recorded: true,
    );
  }

  /// Releases the controller.
  void dispose() => input.dispose();
}
