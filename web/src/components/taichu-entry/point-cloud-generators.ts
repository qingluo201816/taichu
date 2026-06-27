import type {
  GeneratedPointCloudLayer,
  LayerCounts,
  PointCloudLayerName,
} from "./types";

type Color = [number, number, number];

type LayerWriter = {
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

const voidGrey: Color = [0.18, 0.19, 0.18];
const graphite: Color = [0.23, 0.21, 0.23];
const mineralGreen: Color = [0.46, 0.76, 0.46];
const coldMint: Color = [0.68, 0.94, 0.72];
const darkTeal: Color = [0.1, 0.42, 0.38];
const scanCyan: Color = [0.3, 0.66, 0.66];
const starIvory: Color = [0.96, 0.95, 0.86];
const oldBone: Color = [0.78, 0.79, 0.68];
const paleGold: Color = [0.86, 0.86, 0.5];
const emberRose: Color = [0.95, 0.42, 0.58];
const palaceWhite: Color = [0.88, 0.86, 0.78];
const focusGreen: Color = [0.57, 0.82, 0.45];

function mixColor(a: Color, b: Color, t: number): Color {
  const amount = clamp(t, 0, 1);
  return [
    a[0] + (b[0] - a[0]) * amount,
    a[1] + (b[1] - a[1]) * amount,
    a[2] + (b[2] - a[2]) * amount,
  ];
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function ridgeNoise(x: number, z: number): number {
  return (
    Math.sin(x * 0.052 + z * 0.021) * 0.62 +
    Math.sin(x * 0.017 - z * 0.048) * 0.34 +
    Math.cos((x - z) * 0.028) * 0.3
  );
}

function gaussian(value: number, width: number): number {
  return Math.exp(-(value * value) / (2 * width * width));
}

function chooseSegment(random: SeededRandom, segments: Segment[]): Segment {
  const totalWeight = segments.reduce((sum, segment) => sum + segment.weight, 0);
  let cursor = random.range(0, totalWeight);

  for (const segment of segments) {
    cursor -= segment.weight;
    if (cursor <= 0) {
      return segment;
    }
  }

  return segments[segments.length - 1];
}

function createLayer(
  name: PointCloudLayerName,
  count: number,
  seed: number,
  fill: (random: SeededRandom, index: number) => LayerWriter,
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

function scanPointColor(
  random: SeededRandom,
  center: number,
  depth: number,
): Color {
  const palette = random.next();

  if (palette < 0.38) {
    return mixColor(mineralGreen, coldMint, random.next() * 0.54 + center * 0.2);
  }

  if (palette < 0.76) {
    return mixColor(oldBone, starIvory, random.next() * 0.54 + center * 0.3);
  }

  if (palette < 0.87) {
    return mixColor(darkTeal, scanCyan, random.next() * 0.58);
  }

  if (palette < 0.96) {
    return mixColor(voidGrey, paleGold, random.next() * 0.42 + center * 0.18);
  }

  return mixColor(emberRose, starIvory, random.next() * 0.2 + depth * 0.12);
}

export function foregroundGroundPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("foregroundGroundPointCloud", count, 1103, random => {
    const nearBand = random.next() < 0.68;
    const z = nearBand
      ? 4.5 + Math.pow(random.next(), 1.18) * 102
      : 86 + Math.pow(random.next(), 0.78) * 124;
    const depth = z / 210;
    const halfWidth = clamp(46 + z * 1.02, 54, 232);
    const signedX = random.signed();
    const edgeBias = random.next() < 0.28 ? Math.sign(signedX || 1) * Math.pow(Math.abs(signedX), 0.62) : signedX;
    const x = edgeBias * halfWidth;
    const center = gaussian(x, halfWidth * 0.52);
    const basin = gaussian(x, 22) * smoothstep(8, 68, z);
    const y =
      ridgeNoise(x, z) * 0.74 -
      8.2 +
      center * 0.5 -
      basin * 1.4 +
      random.signed() * 0.16;
    const alphaDepth = nearBand ? 1.08 : 0.86;

    return {
      x,
      y,
      z,
      color: scanPointColor(random, center, depth),
      size: random.range(0.58, 2.75) * (1.08 - depth * 0.18),
      alpha: random.range(0.16, 0.42) * alphaDepth * (0.94 + center * 0.26),
      random: random.next(),
    };
  });
}

export function midGroundMistPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("midGroundMistPointCloud", count, 2207, random => {
    const signedX = random.signed();
    const x = Math.sign(signedX || 1) * Math.pow(Math.abs(signedX), 0.72) * 184;
    const z = random.range(64, 186);
    const center = gaussian(x, 78);
    const y =
      random.range(-4.5, 34) +
      Math.sin(z * 0.045 + x * 0.018) * 1.4 -
      center * 1.6;
    const color = random.next() < 0.52
      ? mixColor(darkTeal, coldMint, random.next() * 0.56 + center * 0.14)
      : mixColor(graphite, starIvory, random.next() * 0.54 + center * 0.28);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.38, 1.75),
      alpha: random.range(0.08, 0.25) * (0.88 + center * 0.48),
      random: random.next(),
    };
  });
}

export function horizonGlowBandPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("horizonGlowBandPointCloud", count, 3301, random => {
    const signedX = random.signed();
    const x = Math.sign(signedX || 1) * Math.pow(Math.abs(signedX), 0.58) * 176;
    const z = random.range(124, 178);
    const center = gaussian(x, 62);
    const y =
      random.range(-3.6, 5.6) +
      Math.sin(x * 0.032) * 0.8 +
      random.signed() * center * 0.5;
    const color = random.next() < 0.58
      ? mixColor(oldBone, starIvory, random.next() * 0.34 + center * 0.36)
      : mixColor(mineralGreen, paleGold, random.next() * 0.34 + center * 0.22);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.42, 2.1) * (0.92 + center * 0.22),
      alpha: random.range(0.09, 0.3) * (0.86 + center * 0.48),
      random: random.next(),
    };
  });
}

export function sideBoundaryPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("sideBoundaryPointCloud", count, 4409, random => {
    const side = random.next() > 0.5 ? 1 : -1;
    const z = random.range(24, 248);
    const lobe = random.next();
    const canopyHeight = lobe < 0.64
      ? random.range(15, 94)
      : random.range(-4, 44);
    const wallDistance = random.range(54 + z * 0.12, 190);
    const curve = Math.sin(z * 0.034 + side * 0.7) * 14;
    const x =
      side * wallDistance +
      side * curve +
      random.signed() * random.range(2, 30);
    const y =
      canopyHeight +
      Math.sin(z * 0.048 + x * 0.018) * 7.6 -
      Math.pow(Math.abs(x) / 245, 2) * 9;
    const color = random.next() < 0.68
      ? mixColor(darkTeal, mineralGreen, random.next() * 0.82)
      : mixColor(graphite, coldMint, random.next() * 0.5);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.34, 2.05),
      alpha: random.range(0.08, 0.27) * (lobe < 0.64 ? 1 : 0.84),
      random: random.next(),
    };
  });
}

export function skyDepthPointCloud(count: number): GeneratedPointCloudLayer {
  return createLayer("skyDepthPointCloud", count, 5519, random => {
    const horizonBias = Math.pow(random.next(), 1.95);
    const y = 10 + horizonBias * 104;
    const z = random.range(88, 336);
    const width = 84 + z * 0.65;
    const signedX = random.signed();
    const sideBias = random.next() < 0.38
      ? Math.sign(signedX || 1) * Math.pow(Math.abs(signedX), 0.62)
      : signedX;
    const x = sideBias * width;
    const towardHorizon = 1 - clamp((y - 10) / 104, 0, 1);
    const centerVoid = 1 - gaussian(x, 38) * smoothstep(44, 106, y);
    const color = random.next() < 0.18
      ? mixColor(darkTeal, coldMint, random.next() * 0.46)
      : mixColor([0.1, 0.09, 0.11], oldBone, towardHorizon * 0.5 + random.next() * 0.1);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.28, 1.2),
      alpha: random.range(0.04, 0.16) * (0.68 + towardHorizon * 0.78) * centerVoid,
      random: random.next(),
    };
  });
}

export function ambientDeepSpacePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("ambientDeepSpacePointCloud", count, 6619, random => {
    const z = random.range(128, 366);
    const x = random.signed() * random.range(76, 276);
    const y = random.range(22, 122);
    const edgeLight = smoothstep(52, 190, Math.abs(x));
    const color = random.next() < 0.22
      ? mixColor(darkTeal, scanCyan, random.next() * 0.46)
      : mixColor([0.09, 0.08, 0.1], oldBone, random.next() * 0.34 + edgeLight * 0.12);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.24, 1.0),
      alpha: random.range(0.03, 0.12) * (0.76 + edgeLight * 0.34),
      random: random.next(),
    };
  });
}

export function distantEnvironmentPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("distantEnvironmentPointCloud", count, 7727, random => {
    const x = random.signed() * random.range(20, 172);
    const z = random.range(142, 224);
    const ridge =
      6 +
      Math.sin(x * 0.045) * 4.8 +
      Math.cos(z * 0.038) * 2.7 +
      gaussian(x, 52) * 3.5;
    const y = random.range(-5.5, ridge + random.range(9, 28));
    const center = gaussian(x, 82);
    const color = random.next() < 0.46
      ? mixColor(darkTeal, mineralGreen, random.next() * 0.72)
      : mixColor(voidGrey, starIvory, random.next() * 0.42 + center * 0.14);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.32, 1.45),
      alpha: random.range(0.07, 0.22) * (0.9 + center * 0.22),
      random: random.next(),
    };
  });
}

export function distantPalacePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  const segments: Segment[] = [
    { x1: -49, y1: -0.3, x2: 49, y2: -0.3, z: 186, weight: 9 },
    { x1: -44, y1: 1.0, x2: 44, y2: 1.0, z: 185.4, weight: 6 },
    { x1: -23, y1: 1.0, x2: -23, y2: 10.6, z: 184.6, weight: 4 },
    { x1: 23, y1: 1.0, x2: 23, y2: 10.6, z: 184.6, weight: 4 },
    { x1: -17, y1: 1.2, x2: -17, y2: 8.2, z: 184.2, weight: 3 },
    { x1: 17, y1: 1.2, x2: 17, y2: 8.2, z: 184.2, weight: 3 },
    { x1: -26.5, y1: 8.0, x2: 0, y2: 13.0, z: 183.2, weight: 6 },
    { x1: 0, y1: 13.0, x2: 26.5, y2: 8.0, z: 183.2, weight: 6 },
    { x1: -29, y1: 7.5, x2: 29, y2: 7.5, z: 183.4, weight: 5 },
    { x1: -66, y1: 0.4, x2: -36, y2: 0.4, z: 188.2, weight: 5 },
    { x1: 36, y1: 0.4, x2: 66, y2: 0.4, z: 188.2, weight: 5 },
    { x1: -61, y1: 0.8, x2: -61, y2: 8.0, z: 187.2, weight: 3 },
    { x1: -41, y1: 0.8, x2: -41, y2: 8.0, z: 187.2, weight: 3 },
    { x1: 41, y1: 0.8, x2: 41, y2: 8.0, z: 187.2, weight: 3 },
    { x1: 61, y1: 0.8, x2: 61, y2: 8.0, z: 187.2, weight: 3 },
    { x1: -69, y1: 7.1, x2: -51, y2: 10.2, z: 186.5, weight: 4 },
    { x1: -51, y1: 10.2, x2: -34, y2: 7.1, z: 186.5, weight: 4 },
    { x1: 34, y1: 7.1, x2: 51, y2: 10.2, z: 186.5, weight: 4 },
    { x1: 51, y1: 10.2, x2: 69, y2: 7.1, z: 186.5, weight: 4 },
    { x1: -34, y1: 7.6, x2: -27, y2: 8.7, z: 184.4, weight: 2 },
    { x1: 27, y1: 8.7, x2: 34, y2: 7.6, z: 184.4, weight: 2 },
    { x1: -4, y1: 1.0, x2: -4, y2: 6.2, z: 183.8, weight: 2 },
    { x1: 4, y1: 1.0, x2: 4, y2: 6.2, z: 183.8, weight: 2 },
  ];

  return createLayer("distantPalacePointCloud", count, 8831, random => {
    const selected = chooseSegment(random, segments);
    const t = random.next();
    const x =
      selected.x1 +
      (selected.x2 - selected.x1) * t +
      random.signed() * 0.28;
    const y =
      selected.y1 +
      (selected.y2 - selected.y1) * t +
      random.signed() * 0.22;
    const z = selected.z + random.signed() * 1.35;
    const color = mixColor(palaceWhite, starIvory, random.next() * 0.24);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.36, 1.05),
      alpha: random.range(0.1, 0.26),
      random: random.next(),
    };
  });
}

export function transitionDensePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("transitionDensePointCloud", count, 9917, random => {
    const signedX = random.signed();
    const x = Math.sign(signedX || 1) * Math.pow(Math.abs(signedX), 0.62) * 184;
    const z = random.range(82, 136);
    const center = gaussian(x, 72);
    const y =
      random.range(-12, 42) +
      Math.sin(x * 0.03 + z * 0.06) * 2.2 -
      center * 2;
    const color = random.next() < 0.22
      ? mixColor(mineralGreen, starIvory, center * 0.42)
      : mixColor(oldBone, starIvory, random.next() * 0.36 + center * 0.34);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.38, 2.15) * (0.9 + center * 0.18),
      alpha: random.range(0.04, 0.14) * (0.76 + center * 0.46),
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
    size: 6.4,
    alpha: 0.92,
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
