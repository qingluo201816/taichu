# 技术规格

## 现有前端事实

当前 `web/` 是 Next.js 项目，`src/app` 使用 App Router 结构，`src/components` 已存在组件目录。`package.json` 当前依赖包含 Next、React、Tailwind、shadcn、Tiptap 等，但没有 three/gsap。

## 依赖

```bash
cd web
npm install three gsap
npm install -D @types/three
```

## 推荐文件结构

```text
web/src/components/taichu-entry/
  TaichuEntry.tsx
  point-cloud-scene.ts
  point-cloud-generators.ts
  shaders.ts
  types.ts
  use-reduced-motion.ts
  performance.ts
web/src/app/page.tsx
```

## React/Next 约束

- `TaichuEntry.tsx` 必须是 client component，顶部写 `'use client'`。
- Three.js 初始化只能在 `useEffect` 内进行。
- SSR 阶段不要访问 window/document。
- 组件卸载必须清理 animationFrame、resize listener、geometry、material、renderer。
- `onEnter` 回调用于进入主应用，默认可 `router.push('/editor')`。

## 渲染架构

- WebGLRenderer，alpha false，antialias false 或按性能选择。
- devicePixelRatio clamp 到 1–1.5。
- PerspectiveCamera，FOV idle 约 50–60，进入时收窄到 35–42。
- BufferGeometry 每层一个 Points。
- ShaderMaterial 自定义点 sprite，不用简单 PointsMaterial。
- 不要强 bloom；首版可不用 postprocessing，先靠 shader 点光晕做质感。

## 性能策略

- 按设备分档：low/medium/high。
- high 约 180k 点，medium 约 100k，low 约 60k。
- 移动端默认 low。
- 若运行 2 秒平均 FPS < 45，自动降低天空/ambient/side 粒子可见比例。
- 避免每帧重建 BufferGeometry。
