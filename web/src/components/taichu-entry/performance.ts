import type { LayerCounts, PerformanceTier } from "./types";

const highCounts: LayerCounts = {
  foregroundGroundPointCloud: 72000,
  midGroundMistPointCloud: 38000,
  horizonGlowBandPointCloud: 22000,
  sideBoundaryPointCloud: 64000,
  skyDepthPointCloud: 56000,
  ambientDeepSpacePointCloud: 22000,
  distantEnvironmentPointCloud: 28000,
  distantPalacePointCloud: 8800,
  transitionDensePointCloud: 56000,
  focusParticle: 1,
};

const tierScale: Record<PerformanceTier, number> = {
  high: 1,
  medium: 0.62,
  low: 0.38,
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
