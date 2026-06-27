import type { LayerCounts, PerformanceTier } from "./types";

const highCounts: LayerCounts = {
  foregroundGroundPointCloud: 98000,
  midGroundMistPointCloud: 52000,
  horizonGlowBandPointCloud: 30000,
  sideBoundaryPointCloud: 82000,
  skyDepthPointCloud: 70000,
  ambientDeepSpacePointCloud: 26000,
  distantEnvironmentPointCloud: 36000,
  distantPalacePointCloud: 9600,
  transitionDensePointCloud: 56000,
  focusParticle: 1,
};

const tierScale: Record<PerformanceTier, number> = {
  high: 1,
  medium: 0.52,
  low: 0.3,
};

export function detectPerformanceTier(): PerformanceTier {
  if (typeof window === "undefined") {
    return "medium";
  }

  const isMobile =
    window.matchMedia("(max-width: 760px)").matches ||
    navigator.maxTouchPoints > 1;
  const navigatorWithMemory = navigator as Navigator & { deviceMemory?: number };
  const memory = typeof navigatorWithMemory.deviceMemory === "number"
    ? navigatorWithMemory.deviceMemory
    : 8;
  const cores = navigator.hardwareConcurrency || 4;
  const dpr = window.devicePixelRatio || 1;

  if (isMobile || memory <= 4 || cores <= 4 || dpr > 1.75) {
    return "low";
  }

  if (memory <= 8 || cores <= 8 || dpr > 1.35) {
    return "medium";
  }

  return "high";
}

export function layerCountsForTier(
  tier: PerformanceTier,
  reducedMotion: boolean,
): LayerCounts {
  const scale = reducedMotion ? Math.min(tierScale[tier], 0.32) : tierScale[tier];
  const counts = {} as LayerCounts;

  for (const [name, count] of Object.entries(highCounts)) {
    counts[name as keyof LayerCounts] =
      name === "focusParticle" ? 1 : Math.max(600, Math.round(count * scale));
  }

  return counts;
}
