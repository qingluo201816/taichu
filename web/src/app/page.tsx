import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const modules = [
  {
    title: "章节写作",
    description: "打开当前章节，写作并保存正文",
    href: "/editor",
    size: "lg",
  },
  {
    title: "模型看板",
    description: "用量统计与模型监控",
    href: "/dashboard",
    size: "sm",
  },
  {
    title: "知识库",
    description: "角色、世界观、设定可视化",
    href: "/knowledge",
    size: "sm",
  },
  {
    title: "大纲管理",
    description: "卷、章、情节脉络",
    href: "#",
    size: "sm",
  },
  {
    title: "创作收件箱",
    description: "非事实灵感、待确认设定与章节问题",
    href: "/inbox",
    size: "sm",
  },
  {
    title: "文本审查",
    description: "一致性检查与纠错",
    href: "#",
    size: "sm",
  },
];

export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center p-8 md:p-16">
      <div className="w-full max-w-5xl">
        <header className="mb-12 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900 md:text-5xl dark:text-zinc-50">
            太初
          </h1>
          <p className="mt-3 text-lg text-zinc-500 dark:text-zinc-400">
            玄幻小说 AI 写作助手
          </p>
        </header>

        <div className="grid auto-rows-[160px] grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {modules.map(mod => (
            <Link
              key={mod.title}
              href={mod.href}
              className={`group ${mod.size === "lg" ? "md:col-span-2 md:row-span-2" : ""}`}
            >
              <Card className="h-full border-2 border-zinc-200 transition-colors duration-200 hover:border-zinc-900 dark:border-zinc-800 dark:hover:border-zinc-50">
                <CardHeader>
                  <CardTitle className="text-lg transition-colors group-hover:text-zinc-900 dark:group-hover:text-zinc-50">
                    {mod.title}
                  </CardTitle>
                  <CardDescription className="text-sm">
                    {mod.description}
                  </CardDescription>
                </CardHeader>
                {mod.size === "lg" ? (
                  <CardContent>
                    <div className="flex h-full min-h-[100px] items-center justify-center rounded-lg bg-zinc-50 dark:bg-zinc-900">
                      <span className="text-sm text-zinc-300 dark:text-zinc-700">
                        即将开放
                      </span>
                    </div>
                  </CardContent>
                ) : null}
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
