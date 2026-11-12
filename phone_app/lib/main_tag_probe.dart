import 'package:material_ui/material_ui.dart';

import 'package:wake_alarm_sync/screens/room_proof_screen.dart';

/// Debug entrypoint that opens the room-proof registration screen directly.
///
/// Saves navigating a locked device through Settings during hardware testing;
/// the screen it shows is the real one, reached the normal way in the shipped
/// app via Settings → "Room proof".
///
/// Not part of the shipped app: `flutter build apk` uses `lib/main.dart`.
void main() => runApp(const _TagProbe());

class _TagProbe extends StatelessWidget {
  const _TagProbe();

  @override
  Widget build(BuildContext context) =>
      const MaterialApp(home: RoomProofScreen());
}
