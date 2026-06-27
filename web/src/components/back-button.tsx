"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export default function BackButton() {
  const router = useRouter();

  return (
    <button
      onClick={() => router.push("/home")}
      className="fixed left-5 top-5 z-50 inline-flex h-9 items-center gap-2 rounded-[var(--tc-panel-radius)] border border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-shell)]/85 px-3 text-sm font-medium text-[var(--tc-workspace-text-secondary)] backdrop-blur transition-colors hover:border-[var(--tc-workspace-focus)] hover:text-[var(--tc-workspace-focus)]"
      aria-label="返回太初"
    >
      <ArrowLeft className="w-4 h-4" />
      返回太初
    </button>
  );
}
