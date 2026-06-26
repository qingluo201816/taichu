# 前端编码规范 | 太初 (Taichu) 项目

> 更新日期：2026-06-25
>
> 适用范围：`web/`
>
> 技术栈：Next.js 16 / React 19 / TypeScript / Tailwind CSS 4 / shadcn/ui
>
> 架构基线：`.claude/management/PROJECT_ARCHITECTURE.md`

## 一、核心原则

- **前后端分离**：前端只通过 FastAPI API 使用后端能力。
- **单本小说上下文**：界面始终服务当前唯一小说，不提供小说列表或小说切换器。
- **页面服务场景**：围绕写作、知识库、大纲、灵感和审查等独立场景组织代码。
- **Server Component 优先**：仅将需要交互和浏览器 API 的叶子组件设为 Client Component。
- **统一通信边界**：所有 HTTP 与流式请求通过 `lib/api-client.ts` 和 `lib/api/`。
- **类型安全**：组件 Props、API 请求响应和状态必须有明确类型，禁止 `any`。
- **可扩展但不假装自动化**：通用 Agent 可以动态展示，独立功能页面仍需明确实现。
- **视觉一致**：遵循古风玄幻方向和现有设计系统，不堆砌装饰或复杂导航。

## 二、目标目录结构

```text
web/
├── src/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── page.tsx                   # Bento Grid 首页
│   │   ├── chat/
│   │   │   └── page.tsx
│   │   ├── writing/
│   │   │   └── page.tsx
│   │   ├── outline/
│   │   │   └── page.tsx
│   │   ├── knowledge/
│   │   │   ├── page.tsx
│   │   │   ├── characters/
│   │   │   ├── worldbuilding/
│   │   │   ├── techniques/
│   │   │   ├── locations/
│   │   │   └── timeline/
│   │   ├── inspirations/
│   │   ├── review/
│   │   ├── history/
│   │   └── settings/
│   │
│   ├── components/
│   │   ├── ui/                        # shadcn/ui 基础组件
│   │   ├── layout/                    # 页面框架与返回导航
│   │   ├── chat/
│   │   ├── writing/
│   │   ├── outline/
│   │   ├── knowledge/
│   │   └── review/
│   │
│   ├── hooks/
│   │   ├── use-chat.ts
│   │   ├── use-stream.ts
│   │   └── use-agents.ts
│   │
│   └── lib/
│       ├── api-client.ts              # HTTP/SSE 底层封装
│       ├── api/                       # 按后端资源封装
│       │   ├── agents.ts
│       │   ├── knowledge.ts
│       │   ├── outline.ts
│       │   └── manuscript.ts
│       ├── types/                     # API 与共享类型
│       │   ├── agents.ts
│       │   ├── knowledge.ts
│       │   └── common.ts
│       └── utils.ts
│
├── public/
├── package.json
└── next.config.ts
```

### 职责划分

| 位置 | 职责 | 禁止 |
|---|---|---|
| `app/**/page.tsx` | 路由入口、数据加载、页面组合 | 堆积复杂交互和业务逻辑 |
| `app/**/layout.tsx` | 路由布局和元数据 | 具体业务请求 |
| `components/ui/` | shadcn/ui 基础组件 | 小说业务逻辑 |
| `components/{feature}/` | 功能专用视图组件 | 跨模块访问私有实现 |
| `hooks/` | 客户端状态和交互编排 | 直接拼接 API URL |
| `lib/api-client.ts` | 请求、错误、流式传输底层能力 | 具体页面业务 |
| `lib/api/` | 后端资源级调用函数 | React 状态和 JSX |
| `lib/types/` | API 与共享类型 | 运行时副作用 |

## 三、命名与导出规范

### 文件和目录

| 类型 | 规则 | 示例 |
|---|---|---|
| 路由目录 | kebab-case | `knowledge-base/` |
| Next.js 约定文件 | 框架固定名 | `page.tsx`, `layout.tsx`, `loading.tsx` |
| 组件文件 | kebab-case | `back-button.tsx`, `chat-panel.tsx` |
| shadcn/ui 文件 | 保持生成器命名 | `button.tsx`, `card.tsx` |
| Hook 文件 | `use-{feature}.ts` | `use-chat.ts` |
| API 模块 | 资源名 kebab-case | `knowledge.ts`, `agent-runs.ts` |
| 类型文件 | 资源名 kebab-case | `agents.ts`, `common.ts` |
| 工具文件 | kebab-case | `api-client.ts` |

React 组件、类型和接口使用 PascalCase：

```typescript
interface ChatPanelProps {
  agentName: string;
}

export function ChatPanel({ agentName }: ChatPanelProps) {
  return <section>{agentName}</section>;
}
```

### 默认导出例外

普通组件和工具使用具名导出，便于重构和统一导入。

Next.js 框架约定文件必须遵循框架要求，可以并通常需要默认导出：

```typescript
// app/chat/page.tsx
export default function ChatPage() {
  return <ChatWorkspace />;
}
```

因此规则是：

- `page.tsx`、`layout.tsx`、`loading.tsx`、`error.tsx`、`not-found.tsx` 等遵循 Next.js 约定。
- `components/`、`hooks/`、`lib/` 默认使用具名导出。
- 禁止为了满足“无默认导出”而破坏 Next.js 路由约定。

### 变量和函数

| 类型 | 规则 | 示例 |
|---|---|---|
| 变量 | camelCase | `agentList` |
| 常量 | UPPER_SNAKE_CASE | `API_BASE_URL` |
| 函数 | camelCase，动词开头 | `fetchAgents()` |
| 事件处理 | `handle` 前缀 | `handleSubmit()` |
| 布尔值 | `is` / `has` / `show` / `supports` | `isStreaming` |
| 类型和接口 | PascalCase | `AgentManifestResponse` |
| Props | 组件名 + `Props` | `ChatPanelProps` |

## 四、Server 与 Client Component

`page.tsx` 和 `layout.tsx` 默认保持 Server Component。

只有以下场景使用 `"use client"`：

- `useState`、`useReducer`、`useEffect` 等客户端 Hook。
- 点击、输入、拖拽、快捷键等浏览器交互。
- `window`、`document`、localStorage 等浏览器 API。
- 依赖仅支持客户端运行的第三方库。

```text
page.tsx                     Server Component：数据加载、页面组合
└── writing-workspace.tsx    Client Component：编辑器状态和交互
    ├── chapter-editor.tsx
    └── agent-action-bar.tsx
```

规则：

- 将 Client Component 下推到最小叶子范围。
- 不因一个按钮把整个页面改成 Client Component。
- Client Component 不直接访问服务端环境变量。
- 需要 `metadata` 的交互页面使用 Server `page.tsx` 包裹 Client 组件。

## 五、组件设计规范

- 页面组件负责组合，不承载完整业务流程。
- 功能组件按 `components/{feature}/` 分组。
- 跨功能稳定复用的组件才放 `components/layout/` 或其他共享目录。
- `components/ui/` 仅包含基础 UI，不感知 Agent、角色、大纲等业务概念。
- Props 应保持最小且语义明确，不传入无结构的“大对象”。
- 组件超过约 200 行时检查是否混合状态、请求和展示职责。
- 复杂客户端流程抽取为 Hook；纯格式转换放 `lib/`。
- Loading、Empty、Error、Success 状态必须明确处理。

```typescript
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

interface ChatInputProps {
  isStreaming: boolean;
  onSubmit: (message: string) => Promise<void>;
}

export function ChatInput({ isStreaming, onSubmit }: ChatInputProps) {
  const [message, setMessage] = useState("");

  async function handleSubmit() {
    const content = message.trim();
    if (!content || isStreaming) return;

    await onSubmit(content);
    setMessage("");
  }

  return (
    <div className="flex gap-2">
      <textarea
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="写下你的想法..."
      />
      <Button onClick={handleSubmit} disabled={isStreaming}>
        发送
      </Button>
    </div>
  );
}
```

## 六、API 通信规范

### 唯一通信入口

```typescript
// lib/api-client.ts
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError("请求失败", response.status);
  }

  return response.json() as Promise<T>;
}
```

资源级调用放在 `lib/api/`：

```typescript
// lib/api/agents.ts
import { request } from "@/lib/api-client";
import type { AgentListResponse } from "@/lib/types/agents";

export function fetchAgents(): Promise<AgentListResponse> {
  return request<AgentListResponse>("/api/agents");
}
```

规则：

- 页面、组件和 Hook 禁止自行拼接后端 URL。
- 禁止在组件中散落原始 `fetch`；请求统一封装在 `lib/api/`。
- API 函数返回具体 `Promise<T>`，禁止 `Promise<any>`。
- 统一处理超时、取消、错误结构和认证头。
- 流式响应通过 `api-client.ts` 中的统一 SSE/stream 封装。
- 前端不得直接访问 LLM、MCP、ChromaDB 或 `project_assets/`。
- 后端字段变化必须同步更新前端类型和调用封装。

### Server Component 获取数据

```typescript
import { fetchAgents } from "@/lib/api/agents";

export default async function ChatPage() {
  const { agents } = await fetchAgents();
  return <ChatWorkspace agents={agents} />;
}
```

### Client Component 获取数据

客户端请求通过专用 Hook 管理加载、错误和取消：

```typescript
"use client";

export function AgentSelector() {
  const { agents, error, isLoading } = useAgents();

  if (isLoading) return <AgentSelectorSkeleton />;
  if (error) return <AgentSelectorError error={error} />;
  if (agents.length === 0) return <AgentSelectorEmpty />;

  return <AgentList agents={agents} />;
}
```

## 七、Agent 动态展示边界

后端 Agent Manifest 的传输类型保留 API 原始字段：

```typescript
interface AgentInfoDto {
  name: string;
  label: string;
  description: string;
  exposures: string[];
  required_capabilities: string[];
  supports_streaming: boolean;
}

interface AgentInfo {
  name: string;
  label: string;
  description: string;
  exposures: string[];
  requiredCapabilities: string[];
  supportsStreaming: boolean;
}
```

规则：

- API DTO 保留后端字段命名，`lib/api/agents.ts` 统一映射为前端 camelCase 模型。
- 组件和 Hook 只使用映射后的前端模型，不直接处理 snake_case 转换。
- 通用聊天窗口、操作菜单和 Agent 选择器根据 `exposures` 是否包含 `"ui"` 动态展示。
- 前端不得维护一份与注册中心重复的通用 Agent 固定列表。
- `requiredCapabilities` 用于说明能力和可用性，不用于在前端实现后端权限判断。
- 新增通用 Agent 不应修改通用选择器代码。
- 新增需要专属交互的产品功能，仍需创建独立路由、组件和 API 封装。
- “Agent 自动注册”不等于“前端页面自动生成”。

## 八、状态管理规范

| 状态范围 | 推荐方案 |
|---|---|
| 单组件状态 | `useState` / `useReducer` |
| 父子组件通信 | Props + callback |
| 页面交互流程 | 自定义 Hook |
| 跨页面服务端数据 | 优先由 Server Component 重新获取 |
| 少量应用级客户端状态 | React Context |
| 复杂编辑器状态 | 独立 reducer/store，需先讨论选型 |

规则：

- 不默认引入全局状态库。
- 服务端数据与临时 UI 状态分开管理。
- Hook 返回具名对象，不返回难以理解的位置数组。
- 异步 Hook 必须覆盖 loading、error、data 和取消/卸载场景。
- 不为避免 Props 传递而滥用 Context。

## 九、路由与导航规范

项目固定导航模式：

- 首页使用 Bento Grid 展示主要功能入口。
- 子页面采用全屏沉浸布局。
- 子页面仅保留左上角“返回太初”等必要导航。
- 不设计小说选择页、小说切换器或依赖 `project_id` 的路由。
- “主角”“世界观”“大纲”等入口默认属于当前唯一小说。

```typescript
import type { Metadata } from "next";

import { BackButton } from "@/components/layout/back-button";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export const metadata: Metadata = {
  title: "对话 - 太初",
  description: "与太初讨论玄幻小说创作",
};

export default function ChatPage() {
  return (
    <main className="relative min-h-screen">
      <BackButton />
      <ChatWorkspace />
    </main>
  );
}
```

规则：

- 功能入口页的路由是产品信息架构，不应完全由 Agent 列表替代。
- 每个正式页面提供准确的 `metadata`。
- 动态数据页面提供 `loading.tsx` 和必要的错误边界。
- 路由目录与 URL 使用清晰稳定的英文名称。

## 十、TypeScript 规范

### 类型位置

| 类型 | 位置 |
|---|---|
| API 请求/响应 | `lib/types/{resource}.ts` |
| 单组件 Props | 组件文件内 |
| 功能模块共享类型 | 对应功能的类型文件 |
| 全局通用类型 | `lib/types/common.ts` |

规则：

- 禁止 `any`，未知输入使用 `unknown` 并通过类型守卫收窄。
- API 类型反映传输数据，不直接复制后端领域类概念。
- 使用 `interface` 描述对象结构，联合类型和映射类型使用 `type`。
- 不重复声明同一 API 类型。
- 字符串枚举优先使用联合类型或 `as const`。
- 组件 Props 不使用 `React.FC` 作为默认写法。

```typescript
export const AGENT_EXPOSURES = ["api", "ui", "mcp"] as const;

export type AgentExposure = (typeof AGENT_EXPOSURES)[number];
```

## 十一、样式与视觉规范

使用优先级：

1. Tailwind 工具类。
2. `globals.css` 中的语义化 CSS 变量。
3. shadcn/ui 组件和 variant。
4. Tailwind 难以表达时使用局部 CSS。

规则：

- 颜色、阴影、圆角、间距和字体尽量来自主题令牌。
- 不在业务组件中散落十六进制颜色。
- 条件类名使用 `cn()`。
- 不直接修改 shadcn 组件内部结构来满足单个页面需求，优先扩展 variant。
- 古风玄幻感通过字体、纹理、留白、边框和插图建立，不增加复杂导航。
- 页面必须适配桌面和移动端。
- 动画用于页面进入、状态切换和流式反馈，避免无意义的持续动画。
- 尊重 `prefers-reduced-motion`。

```tsx
import { cn } from "@/lib/utils";

<section
  className={cn(
    "rounded-xl border border-border bg-card text-card-foreground",
    isActive && "ring-2 ring-primary",
  )}
/>
```

## 十二、可访问性与交互

- 使用语义化 HTML，按钮行为使用 `<button>`，导航使用 `<a>`/`Link`。
- 所有表单控件必须有关联 label。
- 图标按钮必须有可访问名称。
- 键盘可完成主要写作操作。
- 焦点样式清晰，弹窗关闭后焦点返回触发元素。
- 颜色对比满足可读性要求，状态不能只靠颜色表达。
- 流式生成区域使用适当的 `aria-live`，避免每个 token 都造成噪声。
- 危险操作需要确认，并明确影响的是源数据还是可重建数据。

## 十三、注释与代码质量

- 导出组件和复杂 Hook 提供简短说明。
- 注释解释设计原因和边界，不复述 JSX。
- 不在代码中记录变更历史。
- 不保留注释掉的旧实现。
- 不复制相同的请求、状态或错误处理逻辑。
- 技术组件替换后同步清理旧依赖、配置、文件和文档。

## 十四、验证与测试

每次前端变更至少执行：

```powershell
npm run lint
npm run build
```

在 `web/` 中运行命令。

需要覆盖的行为：

- Loading、Empty、Error、Success 四态。
- Agent 的 `exposures` 动态展示。
- 流式请求中断、失败与重试。
- 表单校验和危险操作确认。
- 桌面端与移动端主要布局。
- 键盘操作和基本可访问性。

修改 `web/package.json` 或 `web/next.config.ts` 后，还必须验证根目录 `start.bat`。

## 十五、代码审查清单

- [ ] 文件位于目标目录，未把业务组件放进 `components/ui/`
- [ ] 组件文件使用 kebab-case，组件名使用 PascalCase
- [ ] 默认导出仅用于 Next.js 约定或有明确理由的边界
- [ ] Server/Client Component 边界最小且正确
- [ ] HTTP 和流式请求统一通过 `lib/api-client.ts` 与 `lib/api/`
- [ ] 没有直接访问 LLM、MCP、ChromaDB 或 `project_assets/`
- [ ] API 请求响应类型集中且没有 `any`
- [ ] 通用 Agent 展示根据 `exposures` 动态生成
- [ ] 独立产品功能有明确路由和交互，不依赖自动生成页面
- [ ] 未引入小说列表、小说切换器或 `project_id` 路由参数
- [ ] Loading、Empty、Error、Success 状态完整
- [ ] 页面元数据、错误边界和加载状态符合 Next.js 约定
- [ ] 样式使用主题令牌并适配桌面与移动端
- [ ] 主要操作支持键盘和可访问名称
- [ ] `npm run lint` 和 `npm run build` 通过
- [ ] 启动相关变更已验证 `start.bat`

---

**维护者**：Taichu Team
