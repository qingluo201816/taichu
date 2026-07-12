import Link from "next/link";
import {
  ArrowUpRight,
  BookOpen,
  Bot,
  GitBranch,
  Library,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";

const primaryEntries = [
  {
    title: "写作",
    detail: "继续正文创作、章节整理与 AI 协作",
    href: "/editor",
    icon: BookOpen,
  },
  {
    title: "智能体工作台",
    detail: "运行正文知识沉淀并审核候选内容",
    href: "/agent-workbench",
    icon: Bot,
  },
  {
    title: "任务监控",
    detail: "查看执行进度、节点状态与评测结果",
    href: "/task-monitor",
    icon: GitBranch,
  },
  {
    title: "知识库",
    detail: "浏览和维护已确认的结构化知识",
    href: "/knowledge",
    icon: Library,
  },
];

export default function HomePage() {
  return (
    <AppShell activePath="/home" transparentHeader>
      <section className="relative isolate min-h-screen overflow-x-hidden bg-black">
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-30 size-full bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/home/tree-background-static.png')" }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-20 bg-black/25"
        />

        <div className="flex min-h-screen w-full items-center px-5 pb-8 pt-32 md:px-0 xl:pt-24">
          <div className="mx-auto grid w-full max-w-[320px] gap-3 md:mx-0 md:ml-[8vw] md:w-[28vw] md:max-w-none">
            {primaryEntries.map(entry => {
              const Icon = entry.icon;
              return (
                <Link
                  key={entry.href}
                  href={entry.href}
                  className="group flex min-h-28 flex-col justify-between rounded-[var(--tc-radius-card)] border border-white/25 bg-black/20 p-4 transition-colors hover:border-white/45 hover:bg-black/35 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className="inline-flex size-8 items-center justify-center rounded-[var(--tc-radius-control)] border border-white/25 text-white">
                      <Icon className="size-4" />
                    </span>
                    <ArrowUpRight className="size-4 text-white/45 transition-colors group-hover:text-white" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-white">
                      {entry.title}
                    </h2>
                    <p className="mt-1 text-sm leading-5 text-white/70">
                      {entry.detail}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
