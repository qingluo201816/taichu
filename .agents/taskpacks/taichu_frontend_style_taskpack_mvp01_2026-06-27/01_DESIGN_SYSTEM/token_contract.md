# Token 契约

> 更新日期：2026-06-27

目标：把 `TAICHU_DESIGN.md` 中的颜色、字体、间距、半径、阴影、边框、动效抽象成前端可复用 token。

## 推荐 token 分组

建议在 CSS 变量或等价 token 文件中形成以下语义层：

### 色彩

- `--tc-void-*`：入口虚空层。
- `--tc-workspace-*`：深色工作台层。
- `--tc-paper-*`：纸质稿件层。
- `--tc-ink-*`：正文墨色与文字层级。
- `--tc-border-*`：边界线。
- `--tc-accent-*`：低饱和强调色。
- `--tc-danger-*` / `--tc-warning-*` / `--tc-success-*`：状态色，必须克制。

### 字体

- `--tc-font-ui`：界面字体。
- `--tc-font-title`：标题与品牌。
- `--tc-font-manuscript`：正文稿件。
- `--tc-font-mono`：技术/ID/状态。

### 尺寸与间距

- `--tc-shell-sidebar-width`
- `--tc-shell-inspector-width`
- `--tc-editor-max-width`
- `--tc-paper-padding-x`
- `--tc-paper-padding-y`
- `--tc-card-radius`
- `--tc-panel-radius`

### 阴影与边界

- `--tc-shadow-paper`
- `--tc-shadow-panel`
- `--tc-border-subtle`
- `--tc-border-strong`

### 动效

- `--tc-duration-fast`
- `--tc-duration-normal`
- `--tc-duration-slow`
- `--tc-ease-standard`
- `--tc-ease-enter`

## 实现位置

优先在：

- `web/src/app/globals.css`
- `web/src/styles/tokens.css`，如果当前项目已有 styles 目录
- `web/src/lib/design-tokens.ts`，如果组件需要 TS 常量

不要把同一 token 分散写在多个页面里。

## 验收

- 页面中不再大量出现无语义硬编码颜色。
- 组件可以通过 token 统一调整风格。
- 深色工作台和纸质稿件层能明显区分。
- 保留 Tailwind 使用，但颜色应走语义 token 或明确的 theme 映射。
