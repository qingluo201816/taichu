import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const modules = [
  {
    title: "对话写作",
    description: "和 AI 一起构思情节、润色文字",
    href: "/chat",
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
    title: "灵感笔记",
    description: "随手记录的灵感和想法",
    href: "#",
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
    <main className="flex-1 flex items-center justify-center p-8 md:p-16">
      <div className="w-full max-w-5xl">
        <header className="mb-12 text-center">
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            太初
          </h1>
          <p className="mt-3 text-lg text-zinc-500 dark:text-zinc-400">
            玄幻小说 AI 写作助手
          </p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-[160px]">
          {modules.map((mod) => (
            <Link
              key={mod.title}
              href={mod.href}
              className={`group ${mod.size === "lg" ? "md:col-span-2 md:row-span-2" : ""}`}
            >
              <Card className="h-full border-2 border-zinc-200 dark:border-zinc-800 hover:border-zinc-900 dark:hover:border-zinc-50 transition-colors duration-200">
                <CardHeader>
                  <CardTitle className="text-lg group-hover:text-zinc-900 dark:group-hover:text-zinc-50 transition-colors">
                    {mod.title}
                  </CardTitle>
                  <CardDescription className="text-sm">
                    {mod.description}
                  </CardDescription>
                </CardHeader>
                {mod.size === "lg" && (
                  <CardContent>
                    <div className="h-full min-h-[100px] flex items-center justify-center rounded-lg bg-zinc-50 dark:bg-zinc-900">
                      <span className="text-zinc-300 dark:text-zinc-700 text-sm">
                        即将开放
                      </span>
                    </div>
                  </CardContent>
                )}
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
