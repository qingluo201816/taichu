# 太初前端探索规则

## 适用范围

Codex SDD 需求资产探查、设计发现、设计评审和实现验证中，只要涉及 `web/` 的页面、组件、样式、交互、动效、API、类型或用户可见文案，就必须执行本规则。

## 一、强制事实源与边界

### 必读

1. 根 `AGENTS.md` 的前端规则。
2. 根 `DESIGN.md`（唯一前端视觉规则源）。
3. `.agents/skills/taichu-ui-components/SKILL.md`。
4. `web/package.json`、`web/next.config.ts`、`web/tsconfig.json`。
5. 目标页面、组件、API、类型和相关测试。

### 当前技术边界

- Next.js App Router。
- React + TypeScript。
- shadcn/ui 与项目 `components/ui/`。
- Tailwind CSS。
- `motion` 与现有 motion primitives（仅在规则允许且确有价值时）。
- 纯前端，通过 FastAPI `http://127.0.0.1:8000`。
- 桌面浏览器是唯一交付端。
- 所有用户可见文案必须中文。
- 根路径跳转 `/home`，不设计独立入口页例外。
- 不设计原生桌面、手机网页、平板或窄屏重排。

任何与上述边界冲突的旧模板内容无效。

## 二、当前目录模式

按实际仓库确认，不把以下清单当成穷举：

| 职责 | 当前路径模式 |
|---|---|
| 路由入口 | `web/src/app/<route>/page.tsx` |
| 根布局与全局样式 | `web/src/app/layout.tsx`、`web/src/app/globals.css` |
| 应用壳与导航 | `web/src/components/app-shell.tsx`、`web/src/lib/app-shell-navigation.ts` |
| 业务/功能组件 | `web/src/components/<feature>/` |
| 基础 UI | `web/src/components/ui/` |
| 动效原语 | `web/src/components/motion-primitives/` |
| 主题 | `web/src/components/theme/` |
| API 调用 | `web/src/lib/api/*.ts`、`web/src/lib/api-client.ts` |
| 类型契约 | `web/src/lib/types/*.ts` |
| Hooks | `web/src/hooks/` |
| 视图模型/显示适配 | `web/src/lib/<feature>*.ts` |
| 前端测试 | `web/tests/` 与 `web/package.json` 中脚本 |

设计前必须用 `rg --files web/src web/tests` 验证目标路径仍然存在。

## 三、探索步骤

### Step 1：页面与导航定位

1. 在 `web/src/app/` 找到目标路由 `page.tsx`。
2. 读取页面入口，确认它是重定向、薄入口还是包含业务逻辑。
3. 读取 `app-shell-navigation.ts` 和应用壳，确认导航项、选中态、页面标题和操作区。
4. 记录：
   - 路由；
   - 页面入口；
   - 业务 shell/组件；
   - 导航关系；
   - 本次新增、修改或删除类型。
5. 根路径或导航变化必须检查 `/home` 入口决策。

### Step 2：组件层级与职责

从页面入口向下读取真实组件：

- 页面/feature shell；
- feature 子组件；
- `components/ui/` 原语；
- motion primitives；
- 编辑器、监控图、知识列表等专门组件。

输出组件树，例如：

```text
app/<route>/page.tsx
└── FeatureShell
    ├── Header / Toolbar
    ├── DomainPanel
    │   ├── ExistingUiPrimitive
    │   └── FeatureComponent
    └── Feedback / Empty / Error State
```

对每个组件记录：

- 职责；
- props/callback 契约；
- 状态所有权；
- 可复用现有组件；
- 本次是否需要新边界；
- 不应吸收的职责。

### Step 3：组件准入调查

严格按 `taichu-ui-components` Skill：

1. 先确认现有项目组件能否复用。
2. 再确认 shadcn/ui 现有或可安装组件。
3. 花哨效果/动效必须先评估视觉价值、可访问性、维护成本和 `DESIGN.md`。
4. 记录选择、拒绝方案和理由。
5. 不为一次页面任务创建与现有设计系统平行的组件体系。

### Step 4：API 与类型契约

1. 定位 `web/src/lib/api/<domain>.ts`。
2. 读取 `api-client.ts` 的基础请求、错误和响应约定。
3. 定位 `web/src/lib/types/<domain>.ts`。
4. 对照后端 FastAPI 路由和 DTO。
5. 记录：
   - API 函数；
   - HTTP 方法与端点；
   - 请求类型；
   - 响应类型；
   - 错误形状；
   - 加载/空/失败状态；
   - 需要新增还是修改。
6. 禁止 `any`；未知外部数据必须在边界验证/收窄。
7. 不把后端内部英文枚举直接作为用户可见文案。

### Step 5：状态与交互

区分：

- 服务端返回数据；
- 页面级状态；
- 组件局部状态；
- 派生显示状态；
- URL/导航状态；
- 保存/并发/取消中的瞬态；
- 错误与恢复状态。

逐个核心交互记录：

| 用户动作 | 触发组件 | 状态变化 | API/副作用 | 成功反馈 | 失败/恢复 |
|---|---|---|---|---|---|

重点检查：

- 重复提交与禁用状态；
- loading/empty/error/success；
- 保存冲突、取消和重试；
- 删除后普通列表/筛选/搜索不再显示；
- 任务/Agent 运行状态与后端生命周期一致；
- 组件卸载或切换时的竞态。

### Step 6：视觉与内容

对照 `DESIGN.md`：

- 炭灰画布、深色导航、灰色线框、白色胶囊主操作；
- 极光渐变仅少量装饰；
- 页面属于工作台、编辑、资料/知识或对话/智能体哪种模式；
- 信息密度、层级、留白、圆角、边框和排版；
- 按钮、卡片、标签、输入、导航的准入规则；
- 动效节制且服务状态和层级；
- 所有用户可见文案中文；
- 禁止项没有被引入。

不额外设计移动断点、底部导航、触控手势或窄屏折叠。

### Step 7：测试与可验证性

1. 查 `web/package.json` 中现有测试脚本。
2. 查 `web/tests/` 中相同 feature 的测试模式。
3. 确定需要的：
   - 类型/视图模型测试；
   - API 适配测试；
   - 组件/交互测试；
   - 页面手动验收。
4. 运行效果验证固定使用 `http://localhost:3000`。
5. 启动前探测端口；正常本项目服务直接复用。
6. 需要后端时固定 `http://127.0.0.1:8000`。
7. 不通过换端口规避冲突。

## 四、Graphify 使用

当前根图谱是否覆盖 `web/` 必须通过 `.graphify_root` 核对。若不覆盖，不得用后端图谱推断前端关系。

覆盖时：

- 使用当前 `graphify query/path/explain`；
- 记录 `source_location`；
- 回到 TypeScript 源码复核。

不覆盖或不可用时：

```powershell
rg --files web/src web/tests
rg -n "<route|component|api|type|copy>" web/src web/tests
```

Graphify 缺失不是前端探索阻塞。

## 五、输出到 `research.md`

“前端架构分析”至少包含：

1. 页面与导航清单。
2. 组件职责树。
3. 组件复用与准入决策。
4. API/后端端点/请求响应类型映射。
5. 状态所有权和交互表。
6. 视觉规则与用户文案约束。
7. 变更文件规划（新增/修改/删除）。
8. 测试与固定端口验收。
9. 风险、竞态、错误与恢复。
10. Graphify 覆盖/降级说明。

## 六、设计门禁

前端设计不得进入正式 `design.md`，除非：

- 页面入口和组件树来自真实代码；
- API 与类型已对齐；
- 现有组件复用已调查；
- `DESIGN.md` 与组件 Skill 已读取；
- 桌面交付边界明确；
- 中文用户文案明确；
- 状态、错误和恢复可验证；
- 文件路径与测试计划具体；
- 无旧技术栈、移动端或模板化 CRUD 假设。
