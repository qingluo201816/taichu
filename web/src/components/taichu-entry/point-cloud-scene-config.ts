import type { PointCloudSceneConfig } from "./types";

export const taichuEntrySceneConfig: PointCloudSceneConfig = {
  id: "taichu-entry-void",
  asset: {
    assetUrl: "/entry-point-clouds/star-particle-world.ply",
    mobileAssetUrl: "/entry-point-clouds/star-particle-world.ply",
    renderMode: "gaussian-splat",
    position: { x: 0, y: 0, z: 0 },
    rotation: { x: 0, y: 0, z: 0 },
    scale: 1,
  },
  fallbackEnabled: true,
  cameraNav: {
    position: { x: 0, y: -42, z: 132 },
    target: { x: 2, y: -54, z: 500 },
    fov: 68,
  },
  cameraEnter: {
    position: { x: 4, y: -40, z: 164 },
    target: { x: 8, y: -54, z: 536 },
    fov: 64,
  },
  cameraChapter: {
    position: { x: 14, y: -38, z: 196 },
    target: { x: 18, y: -52, z: 580 },
    fov: 60,
  },
  cameraFocus: {
    position: { x: 22, y: -34, z: 232 },
    target: { x: 30, y: -46, z: 616 },
    fov: 56,
  },
  exploration: {
    enabled: false,
    bounds: {
      min: { x: -72, y: -120, z: 82 },
      max: { x: 72, y: 42, z: 184 },
    },
    keyboardSpeed: 62,
    wheelSpeed: 0.2,
    damping: 0.88,
  },
  material: {
    pulseStrength: 0.18,
    audioLow: 0,
    audioMid: 0,
    audioHigh: 0,
  },
  hotspots: [
    {
      id: "world-seed",
      label: "太初之种",
      position: { x: 0.4, y: 18, z: 150 },
      radius: 34,
      chapterId: "entry",
    },
  ],
};
