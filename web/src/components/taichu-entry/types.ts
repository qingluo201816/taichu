export type EntryState =
  | "idle"
  | "entering"
  | "dense-transition"
  | "focus"
  | "completed";

export type PerformanceTier = "low" | "medium" | "high";

export type PointCloudLayerName =
  | "sourcePointCloud"
  | "foregroundGroundPointCloud"
  | "midGroundMistPointCloud"
  | "horizonGlowBandPointCloud"
  | "sideBoundaryPointCloud"
  | "skyDepthPointCloud"
  | "ambientDeepSpacePointCloud"
  | "distantEnvironmentPointCloud"
  | "distantPalacePointCloud"
  | "transitionDensePointCloud"
  | "focusParticle";

export type LayerCounts = Record<PointCloudLayerName, number>;

export type Vec3 = {
  x: number;
  y: number;
  z: number;
};

export type PointCloudAssetFormat = "ply" | "pcd";
export type PointCloudAssetRenderMode = "auto" | "point-cloud" | "gaussian-splat";

export type PointCloudAssetDescriptor = {
  assetUrl: string;
  mobileAssetUrl?: string;
  format?: PointCloudAssetFormat;
  renderMode?: PointCloudAssetRenderMode;
  position?: Vec3;
  rotation?: Vec3;
  scale?: number | Vec3;
};

export type GeneratedPointCloudLayer = {
  name: PointCloudLayerName;
  layerId: number;
  count: number;
  positions: Float32Array;
  colors: Float32Array;
  sizes: Float32Array;
  alphas: Float32Array;
  randoms: Float32Array;
  amplitudes: Float32Array;
};

export type GeneratedGaussianSplatLayer = {
  name: "sourcePointCloud";
  count: number;
  centers: Float32Array;
  colors: Float32Array;
  alphas: Float32Array;
  scales: Float32Array;
  rotations: Float32Array;
  randoms: Float32Array;
  amplitudes: Float32Array;
};

export type LoadedPointCloudAsset =
  | {
      kind: "point-cloud";
      layer: GeneratedPointCloudLayer;
    }
  | {
      kind: "gaussian-splat";
      layer: GeneratedGaussianSplatLayer;
      detailLayer?: GeneratedPointCloudLayer;
      volumeLayers?: GeneratedPointCloudLayer[];
    };

export type PointCloudAssetStatus = "loading" | "loaded" | "fallback";

export type PointCloudCameraPose = {
  position: Vec3;
  target: Vec3;
  fov: number;
};

export type PointCloudExplorationBounds = {
  min: Vec3;
  max: Vec3;
};

export type PointCloudExplorationConfig = {
  enabled: boolean;
  bounds: PointCloudExplorationBounds;
  keyboardSpeed: number;
  wheelSpeed: number;
  damping: number;
};

export type PointCloudHotspot = {
  id: string;
  label: string;
  position: Vec3;
  radius: number;
  chapterId?: string;
};

export type PointCloudMaterialConfig = {
  pulseStrength: number;
  audioLow: number;
  audioMid: number;
  audioHigh: number;
};

export type ForegroundPlanetTexturePaths = {
  albedo: string;
  bump?: string;
  roughness?: string;
  cloudAlpha?: string;
  emission?: string;
  atmosphereGlow?: string;
  particleRing?: string;
  foregroundFog?: string;
  runeCircle?: string;
};

export type ForegroundPlanetConfig = {
  enabled: boolean;
  position: Vec3;
  mobilePosition?: Vec3;
  radius: number;
  mobileRadius?: number;
  opacity: number;
  cloudOpacity: number;
  atmosphereOpacity: number;
  decorOpacity: number;
  rotationSpeed: number;
  cloudRotationSpeed: number;
  tiltDegrees: number;
  enterDrift: Vec3;
  texturePaths: ForegroundPlanetTexturePaths;
};

export type PointCloudSceneConfig = {
  id: string;
  asset: PointCloudAssetDescriptor;
  fallbackEnabled: boolean;
  cameraNav: PointCloudCameraPose;
  cameraEnter: PointCloudCameraPose;
  cameraChapter: PointCloudCameraPose;
  cameraFocus: PointCloudCameraPose;
  exploration: PointCloudExplorationConfig;
  material: PointCloudMaterialConfig;
  foregroundPlanet?: ForegroundPlanetConfig;
  hotspots: PointCloudHotspot[];
};

export type PointCloudSceneOptions = {
  container: HTMLElement;
  reducedMotion: boolean;
  config?: PointCloudSceneConfig;
  onEnter: () => void;
  onStateChange?: (state: EntryState) => void;
  onAssetStatusChange?: (status: PointCloudAssetStatus) => void;
  onCameraPositionChange?: (position: Vec3) => void;
  onRenderError?: (message: string) => void;
};
