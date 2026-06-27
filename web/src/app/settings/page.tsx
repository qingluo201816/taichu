"use client";

import { Download, Loader2, RefreshCcw, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import BackButton from "@/components/back-button";
import { Button } from "@/components/ui/button";
import {
  buildExportBundle,
  clearGeneratedProjection,
  rebuildGeneratedProjection,
} from "@/lib/api/export";
import type {
  ExportBundleResponse,
  IndexBuildJobInfo,
} from "@/lib/types/export";

export default function SettingsPage() {
  const [bundle, setBundle] = useState<ExportBundleResponse | null>(null);
  const [job, setJob] = useState<IndexBuildJobInfo | null>(null);
  const [loading, setLoading] = useState<"export" | "rebuild" | "clear" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  async function exportBundle() {
    setLoading("export");
    setError(null);
    try {
      const response = await buildExportBundle();
      setBundle(response);
      downloadBundle(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出失败");
    } finally {
      setLoading(null);
    }
  }

  async function rebuildGenerated() {
    setLoading("rebuild");
    setError(null);
    try {
      const response = await rebuildGeneratedProjection();
      setJob(response.job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重建失败");
    } finally {
      setLoading(null);
    }
  }

  async function clearGenerated() {
    setLoading("clear");
    setError(null);
    try {
      const response = await clearGeneratedProjection();
      setJob(response.job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "清理失败");
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="min-h-screen bg-[#fbfaf7] px-6 py-7 text-zinc-950">
      <BackButton />
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 pt-12">
        <header className="border-b-2 border-black pb-4">
          <p className="mb-2 text-sm font-semibold text-zinc-600">设置</p>
          <h1 className="text-3xl font-bold">导出与重建</h1>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <ActionPanel
            title="导出"
            detail="导出章节正文、已确认知识、工作区记录与元数据"
            buttonLabel="导出资料包"
            loading={loading === "export"}
            icon={<Download className="size-4" />}
            onClick={exportBundle}
          />
          <ActionPanel
            title="重建"
            detail="清空派生数据后，从源资产重建检索投影"
            buttonLabel="重建派生数据"
            loading={loading === "rebuild"}
            icon={<RefreshCcw className="size-4" />}
            onClick={rebuildGenerated}
          />
          <ActionPanel
            title="清理"
            detail="只清空派生数据，不触碰源资产"
            buttonLabel="清空派生数据"
            loading={loading === "clear"}
            icon={<Trash2 className="size-4" />}
            onClick={clearGenerated}
          />
        </section>

        {error ? (
          <p className="border-2 border-red-700 bg-white p-3 text-sm font-semibold text-red-700">
            {error}
          </p>
        ) : null}

        {job ? (
          <section className="border-2 border-black bg-white p-4">
            <h2 className="text-lg font-bold">最近任务</h2>
            <dl className="mt-3 grid gap-2 text-sm md:grid-cols-2">
              <dt className="font-semibold">动作</dt>
              <dd>{jobActionText(job.action)}</dd>
              <dt className="font-semibold">状态</dt>
              <dd>{jobStatusText(job.status)}</dd>
              <dt className="font-semibold">派生数据路径</dt>
              <dd>{job.generated_path}</dd>
              <dt className="font-semibold">结果</dt>
              <dd>{job.message}</dd>
            </dl>
          </section>
        ) : null}

        {bundle ? (
          <section className="border-2 border-black bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">最近导出</h2>
                <p className="text-sm text-zinc-500">{bundle.id}</p>
              </div>
              <span className="rounded-full border-2 border-black px-3 py-1 text-xs font-semibold">
                {bundle.files.length} 个文件
              </span>
            </div>
            <div className="mt-4 grid gap-2">
              {bundle.files.map(file => (
                <div
                  key={file.path}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border-2 border-black px-3 py-2 text-sm"
                >
                  <span className="break-all font-semibold">{file.path}</span>
                  <span className="text-xs text-zinc-500">
                    {mediaTypeText(file.media_type)}
                  </span>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}

function jobActionText(action: string): string {
  const labels: Record<string, string> = {
    clear: "清空派生数据",
    rebuild: "重建派生数据",
  };
  return labels[action] ?? "任务";
}

function jobStatusText(status: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    failed: "失败",
  };
  return labels[status] ?? "处理中";
}

function mediaTypeText(mediaType: string): string {
  const labels: Record<string, string> = {
    "application/json": "JSON 文件",
    "text/markdown": "Markdown 文件",
    "text/plain": "文本文件",
  };
  return labels[mediaType] ?? "文件";
}

function ActionPanel({
  title,
  detail,
  buttonLabel,
  loading,
  icon,
  onClick,
}: {
  title: string;
  detail: string;
  buttonLabel: string;
  loading: boolean;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <section className="flex min-h-44 flex-col justify-between border-2 border-black bg-white p-4">
      <div>
        <h2 className="text-lg font-bold">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600">{detail}</p>
      </div>
      <Button
        type="button"
        disabled={loading}
        onClick={onClick}
        className="mt-4 rounded-full border-2 border-black"
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
        {buttonLabel}
      </Button>
    </section>
  );
}

function downloadBundle(bundle: ExportBundleResponse) {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${bundle.id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
