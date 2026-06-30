import Link from "next/link";
import { ArrowRight, BookOpen, History, Inbox, Library } from "lucide-react";

import { AppShell } from "@/components/app-shell";

const quickEntries = [
  {
    title: "写作",
    detail: "正文、分卷章节大纲、右侧 AI 入口",
    href: "/editor",
    icon: BookOpen,
  },
  {
    title: "知识库",
    detail: "结构化知识卡片查看与编辑",
    href: "/knowledge",
    icon: Library,
  },
  {
    title: "Inbox",
    detail: "灵感、待确认事实、待处理问题",
    href: "/inbox",
    icon: Inbox,
  },
  {
    title: "AI 历史",
    detail: "写作区多轮记录与提示词快照",
    href: "/ai-history",
    icon: History,
  },
];

export default function HomePage() {
  return (
    <AppShell activePath="/home">
      <section className="mx-auto grid min-h-[calc(100vh-73px)] max-w-6xl content-center gap-10 px-5 py-12">
        <div className="max-w-3xl">
          <p className="mb-3 text-sm font-medium text-[var(--tc-deep-forest-teal)]">
            主创作入口
          </p>
          <h1 className="font-serif text-5xl leading-tight text-[var(--tc-midnight-ink)] md:text-7xl">
            太初
          </h1>
          <p className="mt-5 text-lg leading-8 text-[var(--tc-smoke)]">
            面向单本玄幻小说的个人写作工作台。正文、大纲、知识、灵感和模拟 AI 链路在同一个作者上下文中推进。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {quickEntries.map(entry => {
            const Icon = entry.icon;
            return (
              <Link
                key={entry.href}
                href={entry.href}
                className="group rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-6 transition-colors hover:border-[var(--tc-midnight-ink)]"
              >
                <div className="mb-5 flex items-center justify-between gap-3">
                  <span className="inline-flex size-11 items-center justify-center rounded-[var(--tc-radius-control)] border border-[var(--tc-midnight-ink)] bg-[var(--tc-cream-paper)]">
                    <Icon className="size-5" />
                  </span>
                  <ArrowRight className="size-5 text-[var(--tc-smoke)] transition-transform group-hover:translate-x-1 group-hover:text-[var(--tc-midnight-ink)]" />
                </div>
                <h2 className="text-xl font-semibold text-[var(--tc-midnight-ink)]">
                  {entry.title}
                </h2>
                <p className="mt-2 text-sm leading-6 text-[var(--tc-smoke)]">
                  {entry.detail}
                </p>
              </Link>
            );
          })}
        </div>
      </section>
    </AppShell>
  );
}
