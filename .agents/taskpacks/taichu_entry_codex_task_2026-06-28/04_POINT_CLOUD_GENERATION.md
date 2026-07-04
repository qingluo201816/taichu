# 点云资产管线与备用生成方法

重点：主路径必须是点云资产驱动，支持 `.ply/.pcd/.pcd.gz` 与移动端资产版本。程序生成点云只作为资产读取失败时的备用观测场；即便 fallback 生效，也不要随机撒星星，所有粒子都必须来自空间结构采样。

## 资产主路径

资产主路径至少包含：

- `assetUrl`：桌面点云资产。
- `mobileAssetUrl`：移动端点云资产，可在首版暂时指向同一文件。
- `position / rotation / scale`：资产级变换，不写死到渲染类。
- `sourcePointCloud`：资产加载后的主点云层。
- `focusParticle`：进入完成前吸附的微小粒子。

每个资产点需要归一化为：

```text
position
color
size
alpha
random
amplitude
```

`amplitude` 用于 shader 微动和后续音频/强度信号。没有真实 amplitude 字段时，可以从亮度、深度和稳定 hash 推导默认值。

## fallback 生成方法

## foregroundGroundPointCloud

从轻微起伏地形采样：

- x: [-90, 90]
- z: [5, 160]
- y: noise(x,z) * 1.2 - 8
- 密度随 z 增加而增加，近处稀疏，中远景更密。
- 近相机 0–8 单位死区，不生成高亮点。
- 色彩暖灰白/象牙白，少量暗绿。

## midGroundMistPointCloud

横向雾带：

- x: [-120,120]
- y: [-2,18]
- z: [70,150]
- 中央密度高，两侧渐稀。
- 粒子较小、透明度中等。
- 形成“参考图中部最有空间感的横向粒子层”。

## horizonGlowBandPointCloud

中央亮核：

- 横向带状，贴近地平线。
- 中央暖白/淡金更亮，两侧压暗。
- 不能变成实体光带，仍然必须是离散粒子。

## sideBoundaryPointCloud

左右边界体积：

- 左右两侧生成树冠/山影/位面边界。
- 用椭球体/噪声体积采样，不是垂直墙。
- y 覆盖中上部，z 覆盖中远景。
- alpha 低，负责包裹感。

## skyDepthPointCloud

天空深度：

- 上半部不是空，也不是均匀星空。
- 越靠近地平线越密，越靠顶部越稀。
- z 有真实深度，粒子小、暗、透明。

## distantPalacePointCloud

宫阙最高位面：

用程序函数采样横向宫阙轮廓：

- 中央主殿：矩形体/屋顶斜面/横脊。
- 两侧副阙：小矩形体/小屋顶。
- 飞檐：两侧短斜线/曲线粒子。
- 台基：低矮横向粒子带。

位置远景，z 约 120–150，y 贴近地平线，x 宽度按画面比例调试。粒子稀疏半透明，不填实。

## transitionDensePointCloud

点击后出现/增强的密集位面夹层：

- 初始 alpha 0。
- entering 后逐渐显现。
- 形态是横向极密粒子雾带，不是白屏。
- 进入 focus 前逐渐后退或暗下。
