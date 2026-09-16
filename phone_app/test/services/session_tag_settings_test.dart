import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wake_alarm_sync/services/session_tag_settings.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('starts empty and unconfigured', () async {
    final s = await SessionTagSettings.load();
    expect(s.isConfigured, isFalse);
    expect(s.tagAt(SessionTagSlot.bathroom), isNull);
    expect(s.slotOf('x'), isNull);
  });

  test('saves per slot, stamped, and finds a tag by id', () async {
    await SessionTagSettings.saveTagAt(SessionTagSlot.wardrobe, 'w1');
    final s = await SessionTagSettings.load();
    expect(s.tagAt(SessionTagSlot.wardrobe), 'w1');
    expect(s.tagAt(SessionTagSlot.desk), isNull);
    expect(s.slotOf('w1'), SessionTagSlot.wardrobe);
    expect(s.isConfigured, isTrue);
    expect(DateTime.tryParse(s.editedAt), isNotNull);
  });

  test('replaceAll keeps the given stamp and pads short lists', () async {
    await SessionTagSettings.replaceAll(<String>['b'], '2026-01-01T00:00:00');
    final s = await SessionTagSettings.load();
    expect(s.tagIds, <String>['b', '', '']);
    expect(s.editedAt, '2026-01-01T00:00:00');
  });

  test('malformed storage reads as unset', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      SessionTagSettings.kTagsKey: '{not a list',
    });
    expect((await SessionTagSettings.load()).isConfigured, isFalse);
    SharedPreferences.setMockInitialValues(<String, Object>{
      SessionTagSettings.kTagsKey: '{"a": 1}',
    });
    expect((await SessionTagSettings.load()).isConfigured, isFalse);
  });
}
