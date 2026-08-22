import type { BenchmarkPageQuery } from "./api/general-agent-benchmark";
import type { BenchmarkPage } from "./types/general-agent-benchmark";

export class ServerPaginationState {
  readonly pageSize: number;
  page = 1;
  total = 0;
  totalPages = 0;
  indexRevision = 0;
  totalSnapshot: string | null = null;

  constructor(pageSize: number) {
    this.pageSize = pageSize;
  }

  query(): BenchmarkPageQuery {
    return {
      page: this.page,
      pageSize: this.pageSize,
      ...(this.totalSnapshot ? { totalSnapshot: this.totalSnapshot } : {}),
    };
  }

  goTo(page: number): void {
    this.page = Math.max(1, Math.trunc(page));
  }

  apply<T>(response: BenchmarkPage<T>): number | null {
    this.total = response.total;
    this.totalPages = response.total_pages;
    this.indexRevision = response.index_revision;
    this.totalSnapshot = response.total_snapshot;

    const lastPage = Math.max(1, response.total_pages);
    if (response.items.length === 0 && this.page > lastPage) {
      this.page = lastPage;
      return lastPage;
    }
    this.page = response.page;
    return null;
  }

  refresh(): void {
    this.totalSnapshot = null;
    this.indexRevision = 0;
  }
}
