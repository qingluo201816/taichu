import BackButton from "@/components/back-button";

export default function DashboardPage() {
  return (
    <main className="tc-workspace-page relative flex flex-1 items-center justify-center p-8">
      <BackButton />
      <div className="tc-panel max-w-md px-8 py-10 text-center">
        <p className="mb-3 font-mono text-xs text-[var(--tc-workspace-text-muted)]">
          模型读数 / 待接入
        </p>
        <h2 className="text-2xl font-semibold text-[var(--tc-workspace-focus)]">
          模型看板
        </h2>
        <p className="mt-3 text-sm leading-6 text-[var(--tc-workspace-text-secondary)]">
          当前版本先保留占位，不新增模型管理功能。
        </p>
      </div>
    </main>
  );
}
