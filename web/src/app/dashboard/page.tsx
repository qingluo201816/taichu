import BackButton from "@/components/back-button";

export default function DashboardPage() {
  return (
    <main className="flex-1 flex items-center justify-center p-8 relative">
      <BackButton />
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          模型看板
        </h2>
        <p className="mt-2 text-zinc-500 dark:text-zinc-400">
          即将开放
        </p>
      </div>
    </main>
  );
}
