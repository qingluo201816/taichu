import type {
  GeneratedPointCloudLayer,
  LayerCounts,
  PointCloudLayerName,
} from "./types";

type Color = [number, number, number];

type LayerWriter = {
  index: number;
  x: number;
  y: number;
  z: number;
  color: Color;
  size: number;
  alpha: number;
  random: number;
};

type Segment = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  z: number;
  weight: number;
};

class SeededRandom {
  private seed: number;

  constructor(seed: number) {
    this.seed = seed >>> 0;
  }

  next(): number {
    this.seed = (1664525 * this.seed + 1013904223) >>> 0;
    return this.seed / 4294967296;
  }

  range(min: number, max: number): number {
    return min + (max - min) * this.next();
  }

  signed(): number {
    return this.next() * 2 - 1;
  }
}

const layerIds: Record<PointCloudLayerName, number> = {
  foregroundGroundPointCloud: 1,
  midGroundMistPointCloud: 2,
  horizonGlowBandPointCloud: 3,
  sideBoundaryPointCloud: 4,
  skyDepthPointCloud: 5,
  ambientDeepSpacePointCloud: 6,
  distantEnvironmentPointCloud: 7,
  distantPalacePointCloud: 8,
  transitionDensePointCloud: 9,
  focusParticle: 10,
};

const ivory: Color = [0.76, 0.82, 0.7];
const warmWhite: Color = [0.88, 0.86, 0.78];
const mutedWhite: Color = [0.52, 0.58, 0.53];
const paleGold: Color = [0.72, 0.78, 0.45];
const inkGreen: Color = [0.05, 0.23, 0.14];
const greyGreen: Color = [0.32, 0.62, 0.39];
const scanGreen: Color = [0.48, 0.82, 0.47];
const blueGreen: Color = [0.16, 0.48, 0.45];
const roseDust: Color = [0.82, 0.28, 0.46];
const palaceLine: Color = [0.66, 0.64, 0.6];
const focusGreen: Color = [0.46, 0.68, 0.42];

function mixColor(a: Color, b: Color, t: number): Color {
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function terrainNoise(x: number, z: number): number {
  return (
    Math.sin(x * 0.055 + z * 0.018) * 0.55 +
    Math.sin(x * 0.021 - z * 0.044) * 0.38 +
    Math.cos((x + z) * 0.032) * 0.28
  );
}

function createLayer(
  name: PointCloudLayerName,
  count: number,
  seed: number,
  fill: (random: SeededRandom, index: number) => Omit<LayerWriter, "index">,
): GeneratedPointCloudLayer {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);
  const alphas = new Float32Array(count);
  const randoms = new Float32Array(count);
  const random = new SeededRandom(seed);

  for (let index = 0; index < count; index += 1) {
    const point = fill(random, index);
    const offset = index * 3;
    positions[offset] = point.x;
    positions[offset + 1] = point.y;
    positions[offset + 2] = point.z;
    colors[offset] = point.color[0];
    colors[offset + 1] = point.color[1];
    colors[offset + 2] = point.color[2];
    sizes[index] = point.size;
    alphas[index] = point.alpha;
    randoms[index] = point.random;
  }

  return {
    name,
    layerId: layerIds[name],
    count,
    positions,
    colors,
    sizes,
    alphas,
    randoms,
  };
}

export function foregroundGroundPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("foregroundGroundPointCloud", count, 1103, random => {
    const z = random.next() < 0.62
      ? 6 + Math.pow(random.next(), 1.28) * 106
      : 86 + Math.pow(random.next(), 0.7) * 184;
    const halfWidth = clamp(54 + z * 0.82, 60, 230);
    const x = random.signed() * halfWidth;
    const centerBias = 1 - Math.min(1, Math.abs(x) / halfWidth);
    const y = terrainNoise(x, z) * 1.05 - 7.7 + centerBias * 0.45;
    const depth = z / 270;
    const palette = random.next();
    const color = palette < 0.5
      ? mixColor(greyGreen, scanGreen, random.next() * 0.55)
      : palette < 0.82
        ? mixColor(mutedWhite, ivory, random.next() * 0.85)
        : palette < 0.96
          ? mixColor(inkGreen, greyGreen, random.next() * 0.5)
          : mixColor(roseDust, ivory, random.next() * 0.28);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.95, 3.05) * (1.18 - depth * 0.38),
      alpha: random.range(0.11, 0.34) * (0.92 - depth * 0.22),
      random: random.next(),
    };
  });
}

export function midGroundMistPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("midGroundMistPointCloud", count, 2207, random => {
    const x = random.signed() * 176;
    const z = random.range(78, 220);
    const y = random.range(-4, 36) + Math.sin(z * 0.055) * 1.1;
    const center = 1 - Math.min(1, Math.abs(x) / 176);
    const palette = random.next();
    const color = palette < 0.45
      ? mixColor(blueGreen, scanGreen, random.next() * 0.52)
      : palette < 0.8
        ? mixColor(mutedWhite, warmWhite, center * 0.38 + random.next() * 0.18)
        : mixColor(inkGreen, greyGreen, random.next() * 0.58);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.45, 2.15),
      alpha: random.range(0.035, 0.15) * (0.75 + center * 0.34),
      random: random.next(),
    };
  });
}

export function horizonGlowBandPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("horizonGlowBandPointCloud", count, 3301, random => {
    const x = random.signed() * 136;
    const z = random.range(148, 210);
    const y = random.range(-2.6, 8.8);
    const center = 1 - Math.min(1, Math.abs(x) / 136);
    const color = random.next() < 0.36
      ? mixColor(greyGreen, paleGold, center * 0.42 + random.next() * 0.16)
      : mixColor(mutedWhite, ivory, center * 0.32 + random.next() * 0.24);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.5, 2.2),
      alpha: random.range(0.055, 0.18) * (0.68 + center * 0.34),
      random: random.next(),
    };
  });
}

export function sideBoundaryPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("sideBoundaryPointCloud", count, 4409, random => {
    const side = random.next() > 0.5 ? 1 : -1;
    const z = random.range(28, 245);
    const band = Math.pow(random.next(), 1.25);
    const x = side * random.range(44 + z * 0.1, 182) + random.signed() * 22 * band;
    const yBase = random.range(-8, 90);
    const canopy = Math.sin(z * 0.043 + side) * 8.5;
    const y = yBase + canopy - Math.pow(Math.abs(x) / 230, 2) * 8;
    const color = random.next() < 0.58
      ? mixColor(inkGreen, greyGreen, random.next() * 0.72)
      : mixColor(blueGreen, mutedWhite, random.next() * 0.42);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.35, 2.15),
      alpha: random.range(0.045, 0.22),
      random: random.next(),
    };
  });
}

export function skyDepthPointCloud(count: number): GeneratedPointCloudLayer {
  return createLayer("skyDepthPointCloud", count, 5519, random => {
    const horizonBias = Math.pow(random.next(), 1.35);
    const y = 8 + horizonBias * 92;
    const z = random.range(76, 315);
    const halfWidth = 86 + z * 0.66;
    const x = random.signed() * halfWidth;
    const towardHorizon = 1 - Math.min(1, (y - 8) / 92);
    const color = random.next() < 0.12
      ? mixColor(inkGreen, scanGreen, random.next() * 0.45)
      : mixColor([0.14, 0.12, 0.15], mutedWhite, towardHorizon * 0.52);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.3, 1.55),
      alpha: random.range(0.018, 0.11) * (0.62 + towardHorizon * 0.58),
      random: random.next(),
    };
  });
}

export function ambientDeepSpacePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("ambientDeepSpacePointCloud", count, 6619, random => {
    const z = random.range(110, 350);
    const x = random.signed() * random.range(90, 260);
    const y = random.range(20, 112);
    const color = mixColor([0.11, 0.09, 0.12], greyGreen, random.next() * 0.5);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.25, 1.15),
      alpha: random.range(0.015, 0.075),
      random: random.next(),
    };
  });
}

export function distantEnvironmentPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("distantEnvironmentPointCloud", count, 7727, random => {
    const x = random.signed() * random.range(28, 168);
    const z = random.range(142, 230);
    const ridge = 5 + Math.sin(x * 0.06) * 5.2 + Math.cos(z * 0.045) * 2.4;
    const y = random.range(-5, ridge + 20);
    const color = random.next() < 0.5
      ? mixColor(inkGreen, greyGreen, random.next() * 0.7)
      : mixColor(blueGreen, mutedWhite, random.next() * 0.45);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.35, 1.8),
      alpha: random.range(0.03, 0.14),
      random: random.next(),
    };
  });
}

export function distantPalacePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  const segments: Segment[] = [
    { x1: -31, y1: 0.2, x2: 31, y2: 0.2, z: 194, weight: 6 },
    { x1: -28, y1: 1.3, x2: 28, y2: 1.3, z: 193.2, weight: 5 },
    { x1: -12.5, y1: 1.2, x2: -12.5, y2: 8.9, z: 192.4, weight: 3 },
    { x1: 12.5, y1: 1.2, x2: 12.5, y2: 8.9, z: 192.4, weight: 3 },
    { x1: -15.8, y1: 7.2, x2: 0, y2: 10.2, z: 191.8, weight: 4 },
    { x1: 0, y1: 10.2, x2: 15.8, y2: 7.2, z: 191.8, weight: 4 },
    { x1: -17.4, y1: 6.9, x2: 17.4, y2: 6.9, z: 191.8, weight: 4 },
    { x1: -43, y1: 0.8, x2: -25, y2: 0.8, z: 195.6, weight: 4 },
    { x1: 25, y1: 0.8, x2: 43, y2: 0.8, z: 195.6, weight: 4 },
    { x1: -40, y1: 0.8, x2: -40, y2: 6.8, z: 195, weight: 2 },
    { x1: -27.5, y1: 0.8, x2: -27.5, y2: 6.8, z: 195, weight: 2 },
    { x1: 27.5, y1: 0.8, x2: 27.5, y2: 6.8, z: 195, weight: 2 },
    { x1: 40, y1: 0.8, x2: 40, y2: 6.8, z: 195, weight: 2 },
    { x1: -45, y1: 6.1, x2: -34, y2: 8.1, z: 194.4, weight: 3 },
    { x1: -34, y1: 8.1, x2: -23.5, y2: 6.1, z: 194.4, weight: 3 },
    { x1: 23.5, y1: 6.1, x2: 34, y2: 8.1, z: 194.4, weight: 3 },
    { x1: 34, y1: 8.1, x2: 45, y2: 6.1, z: 194.4, weight: 3 },
    { x1: -23, y1: 6.4, x2: -16.5, y2: 7.3, z: 193.4, weight: 2 },
    { x1: 16.5, y1: 7.3, x2: 23, y2: 6.4, z: 193.4, weight: 2 },
  ];

  const totalWeight = segments.reduce((sum, segment) => sum + segment.weight, 0);

  return createLayer("distantPalacePointCloud", count, 8831, random => {
    let cursor = random.range(0, totalWeight);
    let selected = segments[0];
    for (const segment of segments) {
      cursor -= segment.weight;
      if (cursor <= 0) {
        selected = segment;
        break;
      }
    }

    const t = random.next();
    const x = selected.x1 + (selected.x2 - selected.x1) * t + random.signed() * 0.22;
    const y = selected.y1 + (selected.y2 - selected.y1) * t + random.signed() * 0.2;
    const z = selected.z + random.signed() * 1.8;
    const color = mixColor(palaceLine, warmWhite, random.next() * 0.18);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.45, 1.35),
      alpha: random.range(0.035, 0.12),
      random: random.next(),
    };
  });
}

export function transitionDensePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("transitionDensePointCloud", count, 9917, random => {
    const signed = random.signed();
    const x = Math.sign(signed || 1) * Math.pow(Math.abs(signed), 1.22) * 176;
    const z = random.range(92, 146);
    const y = random.range(-12, 42) + Math.sin(x * 0.035) * 2.4;
    const center = 1 - Math.min(1, Math.abs(x) / 176);
    const color = random.next() < 0.1
      ? mixColor(greyGreen, warmWhite, center * 0.3)
      : mixColor(mutedWhite, warmWhite, center * 0.5);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.45, 2.2),
      alpha: random.range(0.045, 0.15) * (0.68 + center * 0.38),
      random: random.next(),
    };
  });
}

export function focusParticle(): GeneratedPointCloudLayer {
  return createLayer("focusParticle", 1, 10007, () => ({
    x: 0.74,
    y: 4.45,
    z: 132,
    color: focusGreen,
    size: 7.2,
    alpha: 0.86,
    random: 0.42,
  }));
}

export function generatePointCloudLayers(
  counts: LayerCounts,
): GeneratedPointCloudLayer[] {
  return [
    foregroundGroundPointCloud(counts.foregroundGroundPointCloud),
    midGroundMistPointCloud(counts.midGroundMistPointCloud),
    horizonGlowBandPointCloud(counts.horizonGlowBandPointCloud),
    sideBoundaryPointCloud(counts.sideBoundaryPointCloud),
    skyDepthPointCloud(counts.skyDepthPointCloud),
    ambientDeepSpacePointCloud(counts.ambientDeepSpacePointCloud),
    distantEnvironmentPointCloud(counts.distantEnvironmentPointCloud),
    distantPalacePointCloud(counts.distantPalacePointCloud),
    transitionDensePointCloud(counts.transitionDensePointCloud),
    focusParticle(),
  ];
}
