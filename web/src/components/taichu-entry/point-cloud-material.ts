import * as THREE from "three";

import {
  pointCloudFragmentShader,
  pointCloudVertexShader,
} from "./shaders";
import type {
  GeneratedPointCloudLayer,
  PointCloudLayerName,
  PointCloudMaterialConfig,
} from "./types";

const baseLayerOpacity: Record<PointCloudLayerName, number> = {
  sourcePointCloud: 1.04,
  foregroundGroundPointCloud: 0.68,
  midGroundMistPointCloud: 0.76,
  horizonGlowBandPointCloud: 1.18,
  sideBoundaryPointCloud: 1.42,
  skyDepthPointCloud: 0.56,
  ambientDeepSpacePointCloud: 0.3,
  distantEnvironmentPointCloud: 1.52,
  distantPalacePointCloud: 1.28,
  transitionDensePointCloud: 0,
  focusParticle: 0,
};

const layerDrift: Record<PointCloudLayerName, number> = {
  sourcePointCloud: 0.2,
  foregroundGroundPointCloud: 0.34,
  midGroundMistPointCloud: 0.54,
  horizonGlowBandPointCloud: 0.18,
  sideBoundaryPointCloud: 0.36,
  skyDepthPointCloud: 0.18,
  ambientDeepSpacePointCloud: 0.12,
  distantEnvironmentPointCloud: 0.26,
  distantPalacePointCloud: 0.16,
  transitionDensePointCloud: 0.96,
  focusParticle: 0.1,
};

const layerMaxPointSize: Record<PointCloudLayerName, number> = {
  sourcePointCloud: 5.4,
  foregroundGroundPointCloud: 3.6,
  midGroundMistPointCloud: 3.4,
  horizonGlowBandPointCloud: 3.8,
  sideBoundaryPointCloud: 3.8,
  skyDepthPointCloud: 1.9,
  ambientDeepSpacePointCloud: 1.35,
  distantEnvironmentPointCloud: 4.2,
  distantPalacePointCloud: 3.4,
  transitionDensePointCloud: 3.8,
  focusParticle: 7.4,
};

export function layerBaseOpacity(name: PointCloudLayerName): number {
  return baseLayerOpacity[name];
}

export function createPointCloudMaterial({
  layer,
  pixelRatio,
  materialConfig,
}: {
  layer: GeneratedPointCloudLayer;
  pixelRatio: number;
  materialConfig: PointCloudMaterialConfig;
}): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: pointCloudVertexShader,
    fragmentShader: pointCloudFragmentShader,
    transparent: true,
    depthWrite:
      layer.name === "foregroundGroundPointCloud" ||
      layer.name === "horizonGlowBandPointCloud" ||
      layer.name === "distantPalacePointCloud",
    depthTest: true,
    blending: THREE.NormalBlending,
    vertexColors: true,
    uniforms: {
      uTime: { value: 0 },
      uPixelRatio: { value: pixelRatio },
      uEntryProgress: { value: 0 },
      uDenseProgress: { value: 0 },
      uFocusProgress: { value: 0 },
      uGlobalOpacity: { value: baseLayerOpacity[layer.name] },
      uMaxPointSize: { value: layerMaxPointSize[layer.name] },
      uNearFadeDistance: {
        value:
          layer.name === "midGroundMistPointCloud"
            ? 8.8
            : layer.name === "foregroundGroundPointCloud"
            ? 3.2
            : layer.name === "sourcePointCloud"
              ? 4.4
              : 7.2,
      },
      uLayerDrift: { value: layerDrift[layer.name] },
      uFocusDim: {
        value: layer.name === "focusParticle"
          ? 1
          : layer.name === "sourcePointCloud"
            ? 0.2
            : 0.16,
      },
      uAudioLow: { value: materialConfig.audioLow },
      uAudioMid: { value: materialConfig.audioMid },
      uAudioHigh: { value: materialConfig.audioHigh },
      uPulseStrength: { value: materialConfig.pulseStrength },
    },
  });
}
