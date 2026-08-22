import { BenchmarkApiError } from "./api/general-agent-benchmark";

export interface CoordinatedRequest {
  generation: number;
  signal: AbortSignal;
}

export class RequestCoordinator {
  private generation = 0;
  private activeController: AbortController | null = null;
  private appliedRevision = -1;

  get lastAppliedRevision(): number {
    return this.appliedRevision;
  }

  begin(): CoordinatedRequest {
    this.activeController?.abort();
    const controller = new AbortController();
    this.activeController = controller;
    this.generation += 1;
    return {
      generation: this.generation,
      signal: controller.signal,
    };
  }

  apply(
    request: CoordinatedRequest,
    revision: number,
    commit: () => void,
  ): boolean {
    if (
      request.signal.aborted ||
      request.generation !== this.generation ||
      revision < this.appliedRevision
    ) {
      return false;
    }
    commit();
    this.appliedRevision = revision;
    return true;
  }

  cancel(): void {
    this.activeController?.abort();
    this.activeController = null;
  }

  resetRevision(): void {
    this.appliedRevision = -1;
  }
}

export function normalizeBenchmarkRequestError(
  error: unknown,
): string | null {
  if (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  ) {
    return null;
  }
  if (error instanceof BenchmarkApiError) {
    if (error.code === "resource_not_found") {
      return "评测结果尚未准备完成，请稍后刷新。";
    }
    if (error.status >= 500) {
      return "评测服务暂时不可用，请稍后重试。";
    }
    return error.message;
  }
  return "评测请求失败，请稍后重试。";
}
