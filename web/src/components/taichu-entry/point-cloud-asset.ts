import { loadPcdPointCloudLayer } from "./pcd-loader";
import { loadPlyAsset } from "./ply-loader";
import type {
  GeneratedGaussianSplatLayer,
  GeneratedPointCloudLayer,
  LoadedPointCloudAsset,
  PerformanceTier,
  PointCloudAssetDescriptor,
  PointCloudAssetFormat,
  Vec3,
} from "./types";

type LoadPointCloudAssetOptions = {
  tier: PerformanceTier;
  reducedMotion: boolean;
};

function isMobileViewport(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return window.matchMedia("(max-width: 760px)").matches || navigator.maxTouchPoints > 1;
}

function selectedAssetUrl(asset: PointCloudAssetDescriptor): string {
  if (isMobileViewport() && asset.mobileAssetUrl) {
    return asset.mobileAssetUrl;
  }

  return asset.assetUrl;
}

function inferFormat(url: string, fallback?: PointCloudAssetFormat): PointCloudAssetFormat {
  if (fallback) {
    return fallback;
  }

  const normalized = url.toLowerCase();
  if (normalized.endsWith(".pcd") || normalized.endsWith(".pcd.gz")) {
    return "pcd";
  }

  return "ply";
}

function scaleVector(scale: number | Vec3 | undefined): Vec3 {
  if (typeof scale === "number") {
    return { x: scale, y: scale, z: scale };
  }

  return scale ?? { x: 1, y: 1, z: 1 };
}

function rotatePoint(point: Vec3, rotation: Vec3): Vec3 {
  const cx = Math.cos(rotation.x);
  const sx = Math.sin(rotation.x);
  const cy = Math.cos(rotation.y);
  const sy = Math.sin(rotation.y);
  const cz = Math.cos(rotation.z);
  const sz = Math.sin(rotation.z);

  const y1 = point.y * cx - point.z * sx;
  const z1 = point.y * sx + point.z * cx;
  const x2 = point.x * cy + z1 * sy;
  const z2 = -point.x * sy + z1 * cy;
  const x3 = x2 * cz - y1 * sz;
  const y3 = x2 * sz + y1 * cz;

  return { x: x3, y: y3, z: z2 };
}

function applyTransform(
  layer: GeneratedPointCloudLayer,
  asset: PointCloudAssetDescriptor,
): GeneratedPointCloudLayer {
  const position = asset.position ?? { x: 0, y: 0, z: 0 };
  const rotation = asset.rotation ?? { x: 0, y: 0, z: 0 };
  const scale = scaleVector(asset.scale);

  if (
    position.x === 0 &&
    position.y === 0 &&
    position.z === 0 &&
    rotation.x === 0 &&
    rotation.y === 0 &&
    rotation.z === 0 &&
    scale.x === 1 &&
    scale.y === 1 &&
    scale.z === 1
  ) {
    return layer;
  }

  const positions = new Float32Array(layer.positions);
  for (let index = 0; index < layer.count; index += 1) {
    const offset = index * 3;
    const rotated = rotatePoint(
      {
        x: positions[offset] * scale.x,
        y: positions[offset + 1] * scale.y,
        z: positions[offset + 2] * scale.z,
      },
      rotation,
    );

    positions[offset] = rotated.x + position.x;
    positions[offset + 1] = rotated.y + position.y;
    positions[offset + 2] = rotated.z + position.z;
  }

  return { ...layer, positions };
}

function applySplatTransform(
  layer: GeneratedGaussianSplatLayer,
  asset: PointCloudAssetDescriptor,
): GeneratedGaussianSplatLayer {
  const position = asset.position ?? { x: 0, y: 0, z: 0 };
  const rotation = asset.rotation ?? { x: 0, y: 0, z: 0 };
  const scale = scaleVector(asset.scale);

  if (
    position.x === 0 &&
    position.y === 0 &&
    position.z === 0 &&
    rotation.x === 0 &&
    rotation.y === 0 &&
    rotation.z === 0 &&
    scale.x === 1 &&
    scale.y === 1 &&
    scale.z === 1
  ) {
    return layer;
  }

  const centers = new Float32Array(layer.centers);
  const splatScales = new Float32Array(layer.scales);
  for (let index = 0; index < layer.count; index += 1) {
    const offset = index * 3;
    const rotated = rotatePoint(
      {
        x: centers[offset] * scale.x,
        y: centers[offset + 1] * scale.y,
        z: centers[offset + 2] * scale.z,
      },
      rotation,
    );

    centers[offset] = rotated.x + position.x;
    centers[offset + 1] = rotated.y + position.y;
    centers[offset + 2] = rotated.z + position.z;
    splatScales[offset] *= scale.x;
    splatScales[offset + 1] *= scale.y;
    splatScales[offset + 2] *= scale.z;
  }

  return { ...layer, centers, scales: splatScales };
}

function applyAssetTransform(
  loaded: LoadedPointCloudAsset,
  asset: PointCloudAssetDescriptor,
): LoadedPointCloudAsset {
  if (loaded.kind === "gaussian-splat") {
    return {
      kind: "gaussian-splat",
      layer: applySplatTransform(loaded.layer, asset),
      detailLayer: loaded.detailLayer
        ? applyTransform(loaded.detailLayer, asset)
        : undefined,
      volumeLayers: loaded.volumeLayers?.map(layer => applyTransform(layer, asset)),
    };
  }

  return {
    kind: "point-cloud",
    layer: applyTransform(loaded.layer, asset),
  };
}

export async function loadPointCloudAsset(
  asset: PointCloudAssetDescriptor,
  options: LoadPointCloudAssetOptions,
): Promise<LoadedPointCloudAsset> {
  const url = selectedAssetUrl(asset);
  const format = inferFormat(url, asset.format);
  const loaded = format === "pcd"
    ? {
        kind: "point-cloud" as const,
        layer: await loadPcdPointCloudLayer(url, options),
      }
    : await loadPlyAsset(url, {
        ...options,
        renderMode: asset.renderMode ?? "auto",
      });

  return applyAssetTransform(loaded, asset);
}
