import assert from "node:assert/strict";

import {
  buildTextCandidateEdit,
  textCandidateContent,
} from "../../src/lib/editor/ai-card-actions";
import type { AIResultCard } from "../../src/lib/types/ai-cards";

const tests: Array<[string, () => void]> = [];

function test(name: string, run: () => void): void {
  tests.push([name, run]);
}

test("insert cursor operation uses current cursor without touching selection", () => {
  const edit = buildTextCandidateEdit({
    card: textCard(),
    placement: "insert_cursor",
    cursorPosition: 4,
  });

  assert.deepEqual(edit, {
    from: 4,
    to: 4,
    text: "新的正文候选",
  });
});

test("replace selection operation uses card selection range", () => {
  const edit = buildTextCandidateEdit({
    card: textCard(),
    placement: "replace_selection",
    cursorPosition: 99,
  });

  assert.deepEqual(edit, {
    from: 10,
    to: 16,
    text: "新的正文候选",
  });
});

test("append after selection operation inserts after stored range", () => {
  const edit = buildTextCandidateEdit({
    card: textCard(),
    placement: "append_after_selection",
    cursorPosition: 99,
  });

  assert.deepEqual(edit, {
    from: 16,
    to: 16,
    text: "\n\n新的正文候选",
  });
});

test("text candidate content can read object payload fallback", () => {
  const card = textCard({ content: { text: "对象正文" } });

  assert.equal(textCandidateContent(card), "对象正文");
});

for (const [name, run] of tests) {
  run();
  console.log(`ok - ${name}`);
}

function textCard(overrides: Partial<AIResultCard> = {}): AIResultCard {
  return {
    id: "card-1",
    type: "text_candidate",
    workflow: "continue_text",
    status: "generated",
    chapter_id: "chapter_001",
    input_context: {
      mode: "continue_text",
      selected_text: "旧正文",
      selection_range: { from: 10, to: 16 },
    },
    content: "新的正文候选",
    source_refs: [],
    parent_card_id: null,
    created_at: "2026-06-27T00:00:00Z",
    updated_at: "2026-06-27T00:00:00Z",
    ...overrides,
  };
}
