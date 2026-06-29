# 验收清单

## 视觉

- [ ] 初始画面不是星空背景。
- [ ] 下半屏是离散点云地面，不是白色糊块。
- [ ] 中部有横向密集雾带，并且中央亮、两侧暗。
- [ ] 上半部暗而不空，有纵深粒子。
- [ ] 左右有弱包裹粒子体积。
- [ ] 远景宫阙 idle 初始态就存在。
- [ ] 宫阙横向展开、低矮庄重，不像图标/牌坊/拱门。
- [ ] TAICHU 按钮极简，不抢画面。

## 交互

- [ ] 鼠标有轻微视差。
- [ ] Enter/Space 可以触发进入。
- [ ] 点击后先推进。
- [ ] 推进中宫阙淡出。
- [ ] 随后进入密集粒子层。
- [ ] 最后吸附到微小粒子。
- [ ] 完成后进入 `/editor` 或主应用占位。

## 技术

- [ ] 不重复安装 three/gsap/@types/three，确认现有依赖可用。
- [ ] 点云主路径从 `PointCloudSceneConfig.asset` 加载 `.ply/.pcd/.pcd.gz`。
- [ ] 支持 `mobileAssetUrl`，移动端可以选择轻量资产。
- [ ] 程序生成点云只作为资产失败 fallback，不作为主路径。
- [ ] 每个点包含 `amplitude`，shader 能按点强度微动。
- [ ] shader 预留 `uAudioLow/uAudioMid/uAudioHigh/uPulseStrength`。
- [ ] 相机锚点通过 `cameraNav/cameraEnter/cameraChapter/cameraFocus` 配置驱动。
- [ ] 热点/章节锚点进入 `hotspots` 元数据和交互层，不写死到渲染类。
- [ ] `npm run lint` 通过。
- [ ] `npm run build` 通过。
- [ ] Three.js 资源 dispose。
- [ ] 支持 reduced motion。
- [ ] 移动端/低性能有降级。
- [ ] 普通粒子最大点尺寸 clamp <= 6px。
- [ ] 前景粒子有 near-camera fade。
