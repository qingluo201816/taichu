import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  BookOpenCheck,
  Inbox,
  MessageSquare,
  Settings,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const modules = [
  {
    title: "进入编辑器",
    description: "当前章节写作、选区智能助手、章节整理",
    href: "/editor",
    size: "lg",
    icon: BookOpen,
    meta: "主工作台",
  },
  {
    title: "智能对话",
    description: "带来源的深度创作对话",
    href: "/chat",
    size: "sm",
    icon: MessageSquare,
    meta: "事实范围",
  },
  {
    title: "创作收件箱",
    description: "灵感与待确认设定",
    href: "/inbox",
    size: "sm",
    icon: Inbox,
    meta: "非事实",
  },
  {
    title: "知识库",
    description: "作者确认事实",
    href: "/knowledge",
    size: "sm",
    icon: BookOpenCheck,
    meta: "已确认",
  },
  {
    title: "导出与重建",
    description: "导出源资产，重建派生检索数据",
    href: "/settings",
    size: "sm",
    icon: Settings,
    meta: "源资产",
  },
];

export default function HomePage() {
  return (
    <main className="tc-workspace-page flex flex-1 items-center justify-center px-5 py-8 md:px-12 md:py-14">
      <div className="w-full max-w-6xl">
        <header className="mb-8 flex flex-col gap-5 border-b border-[var(--tc-workspace-border-weak)] pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="mb-3 font-mono text-xs text-[var(--tc-workspace-text-muted)]">
              坐标：主创作入口
            </p>
            <h1 className="text-3xl font-semibold tracking-normal text-[var(--tc-workspace-focus)] md:text-4xl">
              太初
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--tc-workspace-text-secondary)] md:text-base">
              单本玄幻长篇的个人 AI 创作工作台。正文、设定、灵感和来源证据在同一上下文中推进。
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="tc-tag px-3 py-1">
              <span className="tc-status-dot" />
              世界种子已点亮
            </span>
            <span className="tc-tag px-3 py-1">深色写作工作台</span>
          </div>
        </header>

        <div className="grid auto-rows-[154px] grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {modules.map(mod => {
            const Icon = mod.icon;
            return (
              <Link
                key={mod.title}
                href={mod.href}
                className={`group ${mod.size === "lg" ? "md:col-span-2 md:row-span-2" : ""}`}
              >
                <Card className="h-full border-[var(--tc-workspace-border-weak)] bg-[var(--tc-workspace-panel)] transition-colors duration-200 hover:border-[var(--tc-workspace-focus)]">
                  <CardHeader>
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <span className="inline-flex size-9 items-center justify-center rounded-[var(--tc-panel-radius)] border border-[var(--tc-workspace-border)] bg-[var(--tc-workspace-recess)] text-[var(--tc-workspace-text-secondary)]">
                        <Icon className="size-4" />
                      </span>
                      <span className="tc-tag px-2.5 py-1">{mod.meta}</span>
                    </div>
                    <CardTitle className="flex items-center justify-between gap-3 text-base text-[var(--tc-workspace-focus)]">
                      {mod.title}
                      <ArrowRight className="size-4 opacity-45 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100" />
                    </CardTitle>
                    <CardDescription className="leading-6">
                      {mod.description}
                    </CardDescription>
                  </CardHeader>
                  {mod.size === "lg" ? (
                    <CardContent>
                      <div className="tc-recess flex min-h-[128px] items-end justify-between px-4 py-3">
                        <span className="font-mono text-xs text-[var(--tc-workspace-text-muted)]">
                          当前章节 / 选区智能助手 / 章节整理
                        </span>
                        <span className="h-px w-20 bg-[var(--tc-aurora-line)]" />
                      </div>
                    </CardContent>
                  ) : null}
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </main>
  );
}
