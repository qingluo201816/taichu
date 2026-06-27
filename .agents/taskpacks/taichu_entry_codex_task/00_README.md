# 太初首屏进入页 Codex 任务包

目标：在 `web/` Next.js 前端内，从零实现一个“太初首次进入页”：第一人称点云地景空间、远景最高位面宫阙、极简 TAICHU 入口按钮、点击后穿越密集粒子层并吸附微小粒子，最后进入主应用。

核心结论：不要继续做“随机星空粒子 + 中央门图标”。参考站 Penderecki's Garden 的关键不是粒子特效，而是真实/拟真实点云场景：点云数据、WebGL/Three.js、GLSL shader、精心压缩和加载、平滑页面转场。太初要复刻的是“点云扫描空间的组织方法”，不是照抄它的素材与内容。

建议 Codex 先读：
1. `01_CODEX_PROMPT.md`：直接投喂给 Codex 的完整任务。
2. `02_VISUAL_SPEC.md`：视觉与动效验收标准。
3. `03_TECH_SPEC.md`：技术架构与文件落位。
4. `04_POINT_CLOUD_GENERATION.md`：点云生成方法，重点避免随机撒星星。
5. `05_ACCEPTANCE_CHECKLIST.md`：完成后逐项自查。

项目事实锚点：当前仓库已有 `web/` Next.js 前端，`web/src/app` 下已有 app 路由目录，`web/src/components` 下已有组件目录；`package.json` 当前尚未包含 three/gsap，需要由 Codex 增加依赖。
