import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

/// Every word painted on screen: text of each RenderParagraph (covers Text,
/// Text.rich, button/chip labels and InputDecoration labels/hints), minus
/// content subtrees.
List<String> wordsOnScreen(WidgetTester tester) {
  final contentElements = <Element>{};
  final allElements = tester.allElements;

  // First pass: collect all content-subtree elements
  for (final element in allElements) {
    if (element.widget.key case ValueKey<String>(
      value: final v,
    ) when v.startsWith('content:')) {
      _collectSubtree(element, contentElements);
    }
    if (element.widget is EditableText) {
      contentElements.add(element);
    }
  }

  final words = <String>[];
  final wordRegex = RegExp(r'\p{L}{2,}', unicode: true);
  final unitRegex = RegExp(r'(\d)\s?(kg|km|min|m|s|h)\b');

  // Second pass: collect words from RenderParagraphs not in content subtrees
  for (final element in allElements) {
    if (contentElements.contains(element)) continue;
    final renderObject = element.renderObject;
    if (renderObject is RenderParagraph) {
      final text = renderObject.text.toPlainText();
      // Strip unit symbols that follow a digit
      final stripped = text.replaceAllMapped(unitRegex, (m) => m.group(1)!);
      for (final match in wordRegex.allMatches(stripped)) {
        words.add(match.group(0)!);
      }
    }
  }

  return words;
}

void _collectSubtree(Element element, Set<Element> out) {
  out.add(element);
  element.visitChildren((child) => _collectSubtree(child, out));
}

/// Fails with the list of words and the screen name.
void expectNoWords(WidgetTester tester, String screen) {
  final words = wordsOnScreen(tester);
  expect(words, isEmpty, reason: 'words on $screen: $words');
  expect(find.byType(Tooltip), findsNothing, reason: 'tooltip on $screen');
}

/// Pixel 6a portrait: 1080x2400 physical at 2.625.
void phoneView(WidgetTester tester) {
  tester.view
    ..physicalSize = const Size(1080, 2400)
    ..devicePixelRatio = 2.625
    ..padding = const FakeViewPadding(top: 132, bottom: 63);
  addTearDown(tester.view.reset);
}
