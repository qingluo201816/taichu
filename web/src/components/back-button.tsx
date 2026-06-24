"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export default function BackButton() {
  const router = useRouter();

  return (
    <button
      onClick={() => router.push("/")}
      className="fixed top-6 left-6 z-50 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-50 transition-colors"
    >
      <ArrowLeft className="w-4 h-4" />
      返回太初
    </button>
  );
}
