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
    title: "进入编辑器",
    description: "当前章节写作、选区智能助手、章节整理",
    href: "/editor",
    size: "lg",
  },
  {
    title: "智能对话",
    description: "带来源的深度创作对话",
    href: "/chat",
    size: "sm",
  },
  {
    title: "创作收件箱",
    description: "灵感与待确认设定",
    href: "/inbox",
    size: "sm",
  },
  {
    title: "知识库",
    description: "作者确认事实",
    href: "/knowledge",
    size: "sm",
  },
  {
    title: "导出与重建",
    description: "导出源资产，重建派生检索数据",
    href: "/settings",
    size: "sm",
  },
];

export default function HomePage() {
  return (
    <main className="flex flex-1 items-center justify-center p-8 md:p-16">
      <div className="w-full max-w-5xl">
        <header className="mb-12 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900 md:text-5xl dark:text-zinc-50">
            太初
          </h1>
          <p className="mt-3 text-lg text-zinc-500 dark:text-zinc-400">
            玄幻小说智能写作助手
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
                        主写作入口
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

