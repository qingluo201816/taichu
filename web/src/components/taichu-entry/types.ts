export type EntryState =
  | "idle"
  | "entering"
  | "dense-transition"
  | "focus"
  | "completed";

export type PerformanceTier = "low" | "medium" | "high";

export type PointCloudLayerName =
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

export type GeneratedPointCloudLayer = {
  name: PointCloudLayerName;
  layerId: number;
  count: number;
  positions: Float32Array;
  colors: Float32Array;
  sizes: Float32Array;
  alphas: Float32Array;
  randoms: Float32Array;
};

export type PointCloudSceneOptions = {
  container: HTMLElement;
  reducedMotion: boolean;
  onEnter: () => void;
  onStateChange?: (state: EntryState) => void;
};

