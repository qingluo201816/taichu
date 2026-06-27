import assert from "node:assert/strict";

import {
  ChapterSaveCoordinator,
  ChapterSaveFailedError,
  isBlockingSaveFailure,
  isDirtySaveSatisfied,
  shouldApplySaveOutcome,
  type ChapterSaveResponse,
} from "../../src/lib/editor/save-coordinator";

type TestChapter = {
  id: string;
};

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

const tests: Array<[string, () => Promise<void> | void]> = [];

function test(name: string, run: () => Promise<void> | void): void {
  tests.push([name, run]);
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

test("save failure blocks dirty chapter switching", async () => {
  const coordinator = new ChapterSaveCoordinator<TestChapter>(async () => {
    throw new Error("disk write failed");
  });

  await assert.rejects(
    () => coordinator.save({ id: "chapter-1" }, "unsaved draft"),
    error => {
      assert.ok(error instanceof ChapterSaveFailedError);
      assert.equal(error.stale, false);
      assert.equal(isBlockingSaveFailure("chapter-1", error), true);
      return true;
    },
  );
});

test("same chapter saves serialize so old content cannot finish after new content", async () => {
  const firstSave = deferred<ChapterSaveResponse<TestChapter>>();
  const secondSave = deferred<ChapterSaveResponse<TestChapter>>();
  const transportCalls: Array<{ chapterId: string; markdown: string }> = [];

  const coordinator = new ChapterSaveCoordinator<TestChapter>(
    (chapterId, markdown) => {
      transportCalls.push({ chapterId, markdown });
      return transportCalls.length === 1 ? firstSave.promise : secondSave.promise;
    },
  );

  const chapter = { id: "chapter-1" };
  const olderOutcomePromise = coordinator.save(chapter, "old draft");
  const newerOutcomePromise = coordinator.save(chapter, "new draft");

  await flushMicrotasks();
  assert.deepEqual(transportCalls, [
    { chapterId: "chapter-1", markdown: "old draft" },
  ]);

  firstSave.resolve({ chapter, markdown: "old draft" });
  const olderOutcome = await olderOutcomePromise;
  await flushMicrotasks();

  assert.equal(olderOutcome.stale, true);
  assert.deepEqual(transportCalls, [
    { chapterId: "chapter-1", markdown: "old draft" },
    { chapterId: "chapter-1", markdown: "new draft" },
  ]);

  secondSave.resolve({ chapter, markdown: "new draft" });
  const newerOutcome = await newerOutcomePromise;

  assert.equal(newerOutcome.stale, false);
  assert.equal(newerOutcome.savedMarkdown, "new draft");
  assert.equal(
    isDirtySaveSatisfied({
      activeChapterId: "chapter-1",
      outcome: olderOutcome,
      editorVersionAtSave: 1,
      currentEditorVersion: 1,
    }),
    false,
  );
  assert.equal(
    isDirtySaveSatisfied({
      activeChapterId: "chapter-1",
      outcome: newerOutcome,
      editorVersionAtSave: 2,
      currentEditorVersion: 2,
    }),
    true,
  );
});

test("saving response from previous chapter cannot re-activate that chapter", () => {
  const outcome = {
    chapter: { id: "chapter-1" },
    chapterId: "chapter-1",
    markdown: "chapter one",
    revision: 1,
    savedMarkdown: "chapter one",
    stale: false,
  };

  assert.equal(shouldApplySaveOutcome("chapter-2", outcome), false);
  assert.equal(
    isDirtySaveSatisfied({
      activeChapterId: "chapter-2",
      outcome,
      editorVersionAtSave: 3,
      currentEditorVersion: 3,
    }),
    false,
  );
});

test("edits made while save is in flight keep the active chapter dirty", () => {
  const outcome = {
    chapter: { id: "chapter-1" },
    chapterId: "chapter-1",
    markdown: "older text",
    revision: 1,
    savedMarkdown: "older text",
    stale: false,
  };

  assert.equal(
    isDirtySaveSatisfied({
      activeChapterId: "chapter-1",
      outcome,
      editorVersionAtSave: 4,
      currentEditorVersion: 5,
    }),
    false,
  );
});

async function run(): Promise<void> {
  for (const [name, runTest] of tests) {
    await runTest();
    console.log(`ok - ${name}`);
  }
}

void run().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
