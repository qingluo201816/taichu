export type ChapterIdentity = {
  id: string;
};

export type ChapterSaveResponse<TChapter extends ChapterIdentity> = {
  chapter: TChapter;
  markdown: string;
};

export type ChapterSaveTransport<TChapter extends ChapterIdentity> = (
  chapterId: string,
  markdown: string,
) => Promise<ChapterSaveResponse<TChapter>>;

export type ChapterSaveOutcome<TChapter extends ChapterIdentity> =
  ChapterSaveResponse<TChapter> & {
    chapterId: string;
    revision: number;
    savedMarkdown: string;
    stale: boolean;
  };

type ChapterSaveFailedErrorOptions = {
  chapterId: string;
  revision: number;
  stale: boolean;
  originalError: unknown;
};

export class ChapterSaveFailedError extends Error {
  readonly chapterId: string;
  readonly revision: number;
  readonly stale: boolean;
  readonly originalError: unknown;

  constructor(options: ChapterSaveFailedErrorOptions) {
    super(errorMessage(options.originalError));
    this.name = "ChapterSaveFailedError";
    this.chapterId = options.chapterId;
    this.revision = options.revision;
    this.stale = options.stale;
    this.originalError = options.originalError;
  }
}

export class ChapterSaveCoordinator<TChapter extends ChapterIdentity> {
  private latestRevisionByChapter = new Map<string, number>();
  private nextRevision = 0;
  private queuesByChapter = new Map<string, Promise<void>>();

  constructor(private readonly transport: ChapterSaveTransport<TChapter>) {}

  save(
    chapter: TChapter,
    markdown: string,
  ): Promise<ChapterSaveOutcome<TChapter>> {
    const chapterId = chapter.id;
    const revision = this.nextRevision + 1;
    this.nextRevision = revision;
    this.latestRevisionByChapter.set(chapterId, revision);

    const previous = this.queuesByChapter.get(chapterId) ?? Promise.resolve();
    const operation = previous.then(async () => {
      try {
        const response = await this.transport(chapterId, markdown);
        return {
          ...response,
          chapterId,
          revision,
          savedMarkdown: markdown,
          stale: this.latestRevisionByChapter.get(chapterId) !== revision,
        };
      } catch (saveError) {
        throw new ChapterSaveFailedError({
          chapterId,
          revision,
          stale: this.latestRevisionByChapter.get(chapterId) !== revision,
          originalError: saveError,
        });
      }
    });

    const queue = operation.then(
      () => undefined,
      () => undefined,
    );
    this.queuesByChapter.set(chapterId, queue);
    void queue.finally(() => {
      if (this.queuesByChapter.get(chapterId) === queue) {
        this.queuesByChapter.delete(chapterId);
      }
    });

    return operation;
  }
}

export function shouldApplySaveOutcome(
  activeChapterId: string | null,
  outcome: Pick<ChapterSaveOutcome<ChapterIdentity>, "chapterId" | "stale">,
): boolean {
  return activeChapterId === outcome.chapterId && !outcome.stale;
}

export function isDirtySaveSatisfied({
  activeChapterId,
  outcome,
  editorVersionAtSave,
  currentEditorVersion,
}: {
  activeChapterId: string | null;
  outcome: Pick<ChapterSaveOutcome<ChapterIdentity>, "chapterId" | "stale">;
  editorVersionAtSave: number;
  currentEditorVersion: number;
}): boolean {
  return (
    shouldApplySaveOutcome(activeChapterId, outcome) &&
    editorVersionAtSave === currentEditorVersion
  );
}

export function isBlockingSaveFailure(
  activeChapterId: string | null,
  failure: ChapterSaveFailedError,
): boolean {
  return activeChapterId === failure.chapterId && !failure.stale;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Chapter save failed";
}
