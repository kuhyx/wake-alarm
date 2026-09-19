import 'package:flutter/material.dart';
import 'package:wake_alarm_sync/services/weight_entry.dart';

/// Five chips, 1 to 5: the morning's energy, tapped next to the weigh-in.
///
/// Chips rather than a field because a rating is a tap, not a number to
/// type. The selected colour is the theme's chip container (a raised ink),
/// deliberately not the gold `primaryContainer`: `scripts/emu_morning.py`
/// finds the submit button by its gold pixels, and a gold chip sat above it
/// was found first -- and the label vanished into it.
class EnergyPicker extends StatelessWidget {
  /// Creates the picker; [selected] is null until a chip is tapped.
  const EnergyPicker({
    required this.selected,
    required this.onSelect,
    super.key,
  });

  /// The chosen level, or null.
  final int? selected;

  /// Called with the tapped level.
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text('Energy', style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: <Widget>[
            for (var level = minEnergy; level <= maxEnergy; level++)
              ChoiceChip(
                label: Text('$level'),
                selected: selected == level,
                selectedColor: scheme.secondaryContainer,
                showCheckmark: false,
                onSelected: (_) => onSelect(level),
              ),
          ],
        ),
      ],
    );
  }
}
