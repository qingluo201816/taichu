# Codex 主任务提示词

你正在修改 `qingluo201816/taichu` 仓库中的 `web/` 前端。请实现“太初点云入口体验引擎”，不要沿用旧的随机粒子 demo 或“程序生成点坐标即主架构”的思路。

## 背景

太初是一款面向单本玄幻长篇小说的 AI 创作工作台。这个首屏不是普通官网，而是第一次进入应用时的仪式感入口：用户先站在一个点云化的玄幻最高位面前，点击 `TAICHU` 后，镜头穿过粒子世界，最终吸附到一个不起眼的小粒子，再进入主应用。

视觉参考站：
```text
https://pendereckisgarden.pl/pl/dwor-mistrza
https://pendereckisgarden.pl/pl/o-projekcie
```
只参考其“点云地景空间、沉浸式进入、平滑转场、深色粒子世界”的方法，不复制素材、文字、建筑、品牌和具体布局。

## 技术方向硬约束

不要做“随机星空背景”。必须做“点云场景渲染”：优先加载点云资产，资产不可用时才用 fallback 构造地面、左右边界、远景宫阙、天空深度层、密集转场层这些三维空间结构并采样点云。

参考站的技术公开信息表明，它不是普通粒子背景，而是使用 TypeScript、Three.js、GLSL，3D 数据以 PCD 点云格式存储并 gzip 压缩，还通过 shader 让粒子运动，并重点处理加载性能和页面转场。太初入口必须以 `.ply/.pcd/.pcd.gz` 点云资产为主路径，程序生成点云只能作为资产读取失败时的备用观测场。

## 需要修改/新增的文件

在 `web/` 内实现。建议按体验引擎分层：

```text
web/src/components/taichu-entry/TaichuEntry.tsx
web/src/components/taichu-entry/point-cloud-scene.ts
web/src/components/taichu-entry/point-cloud-scene-config.ts
web/src/components/taichu-entry/point-cloud-asset.ts
web/src/components/taichu-entry/ply-loader.ts
web/src/components/taichu-entry/pcd-loader.ts
web/src/components/taichu-entry/point-cloud-material.ts
web/src/components/taichu-entry/point-cloud-camera-controller.ts
web/src/components/taichu-entry/point-cloud-interaction-layer.ts
web/src/components/taichu-entry/generated-fallback-point-cloud.ts
web/src/components/taichu-entry/shaders.ts
web/src/components/taichu-entry/types.ts
web/src/components/taichu-entry/use-reduced-motion.ts
web/src/app/page.tsx 或 web/src/app/entry/page.tsx
```

依赖已在当前前端中存在；不要重复引入无关库：
```bash
three
gsap
@types/three
```

如果不用 GSAP，也必须实现同等平滑的状态机动画，但优先使用 GSAP 做相机与 uniform 过渡。

## 页面视觉目标

初始 idle 画面必须是：

1. 深黑偏暖暗底，不是纯黑空幕。
2. 第一人称视角，人眼高度，平视略微俯视。
3. 下半屏 50%–60% 是离散点云地面，不许糊成白块。
4. 中部有横向粒子雾带，中央更亮更密，两侧渐暗渐稀。
5. 左右有弱包裹粒子体积，像树墙/山影/位面边界，不许两边空。
6. 上半部有天空深度粒子层，暗而不空，不能是均匀星空。
7. 远景中部略偏上、贴近地平线位置，存在若隐若现的“最高位面宫阙”。
8. 顶部中央悬浮极简白色/暖白描边按钮，文字 `TAICHU`。

一句话标准：不要“星空里一个门”，要“第一人称点云地景里，远处地平线上若隐若现的宫阙最高位面”。

## 宫阙主体要求

不要做普通门洞、牌坊、图标、拱门、细长天门。要做远景“最高位面宫阙”，横向展开，低矮庄重，半透明融入环境。

结构包括：

1. 中央主殿/主门楼。
2. 横向屋脊。
3. 两侧副阙。
4. 轻微飞檐。
5. 底部台基。

尺寸：宽度约占画面 18%–22%，高度约占画面 8%–10%。位置：贴近地平线，略高于地平线。粒子密度要低，透明度要低，不要填太实，不要比环境亮太多。

## 点云层必须拆分

必须在资产主路径与 fallback 中有清晰命名：

```text
foregroundGroundPointCloud
midGroundMistPointCloud
horizonGlowBandPointCloud
sideBoundaryPointCloud
skyDepthPointCloud
ambientDeepSpacePointCloud
distantEnvironmentPointCloud
distantPalacePointCloud
transitionDensePointCloud
focusParticle
```

资产主路径至少支持 `sourcePointCloud` 与 `focusParticle`；fallback 才负责生成多层观测场。每一层要有独立的 geometry、material/uniform 或至少独立 attributes，便于调参。

## Shader 要求

使用 Three.js `BufferGeometry` + 自定义 `ShaderMaterial`。每个点至少包含：

```text
position: vec3
color: vec3
size: float
alpha: float
random: float
amplitude: float
layerId: float 或通过独立 material 区分
```

顶点 shader 必须：

1. 支持透视点大小变化。
2. 对点大小做 clamp，普通粒子最大不要超过 6px。
3. 支持时间驱动的轻微漂浮/呼吸，但不能变成水波网格。
4. 支持进入动画时沿 z 轴/相机方向拉伸。
5. 支持 near-camera fade，避免前景糊屏。
6. 预留 `uAudioLow/uAudioMid/uAudioHigh/uPulseStrength`，让后续音频或强度信号能驱动每点 amplitude。

片元 shader 必须：

1. 使用圆形点 sprite。
2. 边缘柔和，但中心不要过曝。
3. 支持 alpha。
4. 避免 additive 叠爆；默认使用 NormalBlending 或非常克制的 AdditiveBlending。

## 粒子参数建议

总粒子目标：桌面 120k–220k，自适应降级到 60k–100k。

层级建议：

```text
foregroundGround: 25k–45k，size 1.2–5.0，alpha 0.06–0.16
midGroundMist: 25k–45k，size 0.8–3.2，alpha 0.08–0.22
horizonGlowBand: 12k–25k，size 0.9–3.5，alpha 0.08–0.24
sideBoundary: 25k–50k，size 0.6–2.8，alpha 0.04–0.18
skyDepth: 25k–55k，size 0.5–2.4，alpha 0.03–0.14
ambientDeepSpace: 10k–30k，size 0.4–1.6，alpha 0.02–0.08
distantPalace: 3k–8k，size 0.6–2.0，alpha 0.05–0.18
transitionDense: 40k–80k，初始隐藏，进入阶段启用
```

前景地面禁止过曝：不使用纯 #ffffff，主色用暖灰白/象牙白/灰白。下半屏不能比中部地平线亮带更抢眼。

## 动画状态机

必须实现：

```ts
type EntryState = 'idle' | 'entering' | 'dense-transition' | 'focus' | 'completed'
```

流程：

1. `idle`：点云地景缓慢漂浮。远景宫阙从一开始就若隐若现存在。TAICHU 按钮可点击。
2. `entering`：点击 TAICHU 后，相机沿地面方向向远景推进，前景地面粒子从下方与两侧掠过。宫阙逐渐淡出，不要真的进入宫阙。
3. `dense-transition`：进入一层极密横向粒子雾带/位面夹层，短暂看不清结构，产生空间迷失感。
4. `focus`：从密层里锁定一颗不起眼的微小粒子，其他粒子渐暗或后退。微粒可有极克制的暗绿 glow。
5. `completed`：触发 `onEnter` 回调，默认跳转 `/home` 或当前主应用入口，不要白屏卡住。

相机锚点必须进入 `PointCloudSceneConfig`，至少包含 `cameraNav`、`cameraEnter`、`cameraChapter`、`cameraFocus`，不要散落写死在渲染类里。

## 场景元数据

必须提供 `PointCloudSceneConfig`：

```text
assetUrl
mobileAssetUrl
position / rotation / scale
cameraNav
cameraEnter
cameraChapter
cameraFocus
hotspots
```

`hotspots` 是后续章节锚点/世界节点的入口，首版可以只提供元数据和命中接口，不必做复杂 UI。

## UI 与可用性

1. TAICHU 按钮：顶部中央，极简细描边，暖白，不要复杂装饰。
2. 支持键盘：Enter/Space 触发进入。
3. 支持 `prefers-reduced-motion`：低动效模式下不播放长俯冲，只淡出进入。
4. 支持低性能模式：根据 DPR、移动设备、帧率降粒子数量。
5. 组件卸载时 dispose geometry/material/renderer，避免内存泄漏。

## 验收重点

1. 画面不能像星空背景。
2. 画面不能下半部分糊成白块。
3. 上半部分不能大面积空黑。
4. 天门/宫阙必须 idle 初始态就存在。
5. 宫阙不能像图标，必须融入远景环境。
6. 点击后必须先推进，再穿越密层，再吸附微粒。
7. `npm run lint` 和 `npm run build` 通过。
