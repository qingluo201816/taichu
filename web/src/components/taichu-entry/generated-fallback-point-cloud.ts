import type {
  GeneratedPointCloudLayer,
  LayerCounts,
  PointCloudLayerName,
} from "./types";

type Color = [number, number, number];

type Vec3 = {
  x: number;
  y: number;
  z: number;
};

type LayerWriter = Vec3 & {
  color: Color;
  size: number;
  alpha: number;
  random: number;
  amplitude?: number;
};

type TreeCrown = {
  center: Vec3;
  radius: Vec3;
  side: -1 | 1;
};

type FlowerClump = {
  x: number;
  z: number;
  radiusX: number;
  radiusZ: number;
  height: number;
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
  sourcePointCloud: 11,
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

const inkGreen: Color = [0.012, 0.055, 0.035];
const deepMoss: Color = [0.028, 0.14, 0.072];
const grassGreen: Color = [0.1, 0.38, 0.16];
const tenderGreen: Color = [0.46, 0.68, 0.22];
const shadowBrown: Color = [0.11, 0.095, 0.08];
const roseShadow: Color = [0.15, 0.025, 0.1];
const roseDeep: Color = [0.33, 0.045, 0.15];
const roseMid: Color = [0.68, 0.2, 0.36];
const rosePale: Color = [0.95, 0.62, 0.68];
const treeBlue: Color = [0.055, 0.18, 0.22];
const treeGreen: Color = [0.12, 0.46, 0.3];
const treeMist: Color = [0.5, 0.72, 0.62];
const pathWhite: Color = [0.78, 0.82, 0.78];
const coldWhite: Color = [0.86, 0.88, 0.9];
const stoneGrey: Color = [0.5, 0.5, 0.48];
const stoneWarm: Color = [0.68, 0.62, 0.52];
const airBlue: Color = [0.07, 0.1, 0.17];
const warmSignal: Color = [0.86, 0.94, 0.56];

const treeCrowns: TreeCrown[] = [
  { side: -1, center: { x: -470, y: 86, z: 410 }, radius: { x: 190, y: 138, z: 116 } },
  { side: -1, center: { x: -330, y: 104, z: 500 }, radius: { x: 155, y: 132, z: 112 } },
  { side: -1, center: { x: -190, y: 112, z: 600 }, radius: { x: 150, y: 118, z: 104 } },
  { side: 1, center: { x: 230, y: 108, z: 585 }, radius: { x: 160, y: 122, z: 112 } },
  { side: 1, center: { x: 382, y: 104, z: 500 }, radius: { x: 172, y: 136, z: 116 } },
  { side: 1, center: { x: 540, y: 88, z: 410 }, radius: { x: 205, y: 142, z: 124 } },
  { side: -1, center: { x: -48, y: 118, z: 680 }, radius: { x: 250, y: 96, z: 82 } },
];

const flowerClumps: FlowerClump[] = [
  { x: -330, z: 168, radiusX: 88, radiusZ: 42, height: 9 },
  { x: -188, z: 224, radiusX: 76, radiusZ: 46, height: 12 },
  { x: -80, z: 152, radiusX: 62, radiusZ: 38, height: 8 },
  { x: 82, z: 188, radiusX: 78, radiusZ: 42, height: 10 },
  { x: 202, z: 240, radiusX: 86, radiusZ: 48, height: 12 },
  { x: 356, z: 176, radiusX: 96, radiusZ: 44, height: 9 },
  { x: -250, z: 314, radiusX: 72, radiusZ: 34, height: 7 },
  { x: 294, z: 328, radiusX: 82, radiusZ: 38, height: 8 },
];

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function gaussian(value: number, width: number): number {
  return Math.exp(-(value * value) / (2 * width * width));
}

function mixColor(a: Color, b: Color, amount: number): Color {
  const t = clamp(amount, 0, 1);
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
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
  const amplitudes = new Float32Array(count);
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
    amplitudes[index] =
      point.amplitude ??
      clamp(point.alpha * 2.4 + point.size * 0.035 + point.random * 0.18, 0.04, 1);
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
    amplitudes,
  };
}

function pathCenterX(z: number): number {
  return Math.sin(z * 0.009 + 0.4) * 22 - smoothstep(260, 650, z) * 18;
}

function pathWidth(z: number): number {
  return 104 - smoothstep(60, 650, z) * 72;
}

function gardenWidth(z: number): number {
  return 70 + z * 1.03;
}

function groundY(x: number, z: number): number {
  const longWave = Math.sin(x * 0.009 + z * 0.013) * 1.28;
  const shortWave = Math.sin(x * 0.038 - z * 0.025) * 0.52;
  const pathDip = gaussian(x - pathCenterX(z), pathWidth(z) * 0.62) * 0.82;

  return -16.2 + longWave + shortWave - pathDip;
}

function sizeByDepth(random: SeededRandom, z: number, min: number, max: number): number {
  const near = 1 - smoothstep(26, 720, z);
  const emphasis = random.next() > 0.91 ? random.range(0.8, 1.45) : random.range(0.42, 0.92);

  return min + (max - min) * near * emphasis + random.range(0, 0.24);
}

function groundColor(random: SeededRandom, x: number, z: number): Color {
  const pathInfluence = gaussian(x - pathCenterX(z), pathWidth(z) * 1.2);
  const light =
    gaussian(Math.sin(x * 0.016 + z * 0.012), 0.32) * 0.36 +
    pathInfluence * 0.18;
  const shade =
    gaussian(Math.sin(x * 0.026 - z * 0.02), 0.23) * 0.32 +
    smoothstep(480, 760, z) * 0.22;
  const base = random.next() < 0.16 + shade * 0.32 ? shadowBrown : inkGreen;
  const mid = mixColor(base, grassGreen, random.range(0.24, 0.82) + light * 0.16);

  if (random.next() < 0.16 + light * 0.36) {
    return mixColor(mid, tenderGreen, random.range(0.12, 0.58));
  }

  return mixColor(mid, deepMoss, shade * 0.24);
}

function flowerColor(random: SeededRandom, lift: number): Color {
  const base = random.next() < 0.22 ? roseShadow : roseDeep;
  const mid = mixColor(base, roseMid, random.range(0.28, 0.92));

  if (random.next() < 0.22 + lift * 0.34) {
    return mixColor(mid, rosePale, random.range(0.12, 0.68));
  }

  return mid;
}

function treeColor(random: SeededRandom, highlight: number): Color {
  const cool = mixColor(treeBlue, treeGreen, random.range(0.2, 0.86));

  if (random.next() < 0.18 + highlight * 0.34) {
    return mixColor(cool, treeMist, random.range(0.2, 0.76));
  }

  if (random.next() < 0.16) {
    return mixColor(cool, tenderGreen, random.range(0.08, 0.3));
  }

  return cool;
}

function facadeColor(random: SeededRandom, edge: number): Color {
  const stone = mixColor(stoneGrey, stoneWarm, random.range(0.12, 0.64));

  if (random.next() < 0.38 + edge * 0.28) {
    return mixColor(stone, coldWhite, random.range(0.18, 0.78) + edge * 0.16);
  }

  return stone;
}

function sampleGround(random: SeededRandom): Vec3 {
  const z = 18 + Math.pow(random.next(), 1.42) * 720;
  const width = gardenWidth(z);
  const x = random.signed() * width * Math.pow(random.next(), 0.2);

  return {
    x,
    y: groundY(x, z) + random.signed() * random.range(0.02, 0.3),
    z,
  };
}

function pickFlowerClump(random: SeededRandom): FlowerClump {
  const index = Math.min(
    flowerClumps.length - 1,
    Math.floor(random.next() * flowerClumps.length),
  );

  return flowerClumps[index];
}

function sampleFlower(random: SeededRandom): LayerWriter {
  const clump = pickFlowerClump(random);
  const angle = random.range(0, Math.PI * 2);
  const radius = Math.pow(random.next(), 0.54);
  const x = clump.x + Math.cos(angle) * clump.radiusX * radius;
  const z = clump.z + Math.sin(angle) * clump.radiusZ * radius + random.signed() * 9;
  const mound = 1 - radius;
  const lift = Math.pow(random.next(), 1.7) * clump.height * (0.42 + mound);
  const y = groundY(x, z) + 0.8 + lift + random.signed() * 0.62;
  const near = 1 - smoothstep(110, 360, z);

  return {
    x,
    y,
    z,
    color: flowerColor(random, mound),
    size: random.range(0.52, 1.9) + near * random.range(0.4, 2.1),
    alpha: random.range(0.26, 0.7) * (0.7 + mound * 0.24),
    random: random.next(),
  };
}

function samplePath(random: SeededRandom): LayerWriter {
  const z = 64 + Math.pow(random.next(), 1.18) * 590;
  const center = pathCenterX(z);
  const width = pathWidth(z);
  const lateral = random.signed() * width * Math.pow(random.next(), 0.72);
  const edge = Math.abs(lateral) / Math.max(1, width);
  const x = center + lateral + Math.sin(z * 0.018) * 4;
  const y = groundY(x, z) + random.range(0.18, 1.7);
  const centerGlow = 1 - edge;
  const color = mixColor(
    mixColor(pathWhite, tenderGreen, random.range(0.02, 0.22)),
    coldWhite,
    centerGlow * random.range(0.16, 0.54),
  );

  return {
    x,
    y,
    z,
    color,
    size: sizeByDepth(random, z, 0.32, 2.7),
    alpha: random.range(0.16, 0.52) * (0.72 + centerGlow * 0.34),
    random: random.next(),
  };
}

function pickTreeCrown(random: SeededRandom): TreeCrown {
  const roll = random.next();

  if (roll < 0.18) {
    return treeCrowns[0];
  }
  if (roll < 0.32) {
    return treeCrowns[1];
  }
  if (roll < 0.45) {
    return treeCrowns[2];
  }
  if (roll < 0.58) {
    return treeCrowns[3];
  }
  if (roll < 0.74) {
    return treeCrowns[4];
  }
  if (roll < 0.9) {
    return treeCrowns[5];
  }

  return treeCrowns[6];
}

function sampleTreeSurface(random: SeededRandom, crown: TreeCrown): Vec3 {
  const theta = random.range(0, Math.PI * 2);
  const phi = Math.acos(random.range(-0.82, 0.92));
  const shell = random.range(0.62, 1) * (random.next() < 0.72 ? 1 : random.range(0.72, 0.92));
  const x = crown.center.x + Math.cos(theta) * Math.sin(phi) * crown.radius.x * shell;
  const y =
    crown.center.y +
    Math.cos(phi) * crown.radius.y * shell +
    Math.sin(theta * 2.1) * random.range(0, 12);
  const z =
    crown.center.z +
    Math.sin(theta) * Math.sin(phi) * crown.radius.z * shell +
    random.signed() * random.range(0, 18);

  return { x, y, z };
}

function sampleShrub(random: SeededRandom): LayerWriter {
  const z = random.range(255, 610);
  const side = random.next() < 0.5 ? -1 : 1;
  const centerX = pathCenterX(z) + side * random.range(pathWidth(z) * 1.3, gardenWidth(z) * 0.62);
  const radiusX = random.range(32, 78);
  const radiusZ = random.range(18, 52);
  const angle = random.range(0, Math.PI * 2);
  const radius = Math.pow(random.next(), 0.48);
  const x = centerX + Math.cos(angle) * radiusX * radius;
  const pointZ = z + Math.sin(angle) * radiusZ * radius;
  const height = random.range(3, 30) * Math.pow(random.next(), 0.55);
  const y = groundY(x, pointZ) + height;
  const edgeLight = gaussian(Math.abs(x) - 220, 130) * 0.22;

  return {
    x,
    y,
    z: pointZ,
    color: treeColor(random, edgeLight),
    size: sizeByDepth(random, pointZ, 0.34, 2.8),
    alpha: random.range(0.1, 0.34),
    random: random.next(),
  };
}

function sampleTreeOrShrub(random: SeededRandom): LayerWriter {
  if (random.next() < 0.22) {
    return sampleShrub(random);
  }

  const crown = pickTreeCrown(random);
  const point = sampleTreeSurface(random, crown);
  const centerOpening = gaussian(point.x, 118) * gaussian(point.z - 590, 115);
  const verticalLight = smoothstep(12, crown.radius.y * 1.42, point.y - (crown.center.y - crown.radius.y));
  const sideLight = smoothstep(160, 520, Math.abs(point.x));

  return {
    ...point,
    color: treeColor(random, verticalLight * 0.3 + sideLight * 0.12),
    size: sizeByDepth(random, point.z, 0.32, 2.75) + sideLight * random.range(0, 0.58),
    alpha: random.range(0.12, 0.46) * (1 - centerOpening * 0.36),
    random: random.next(),
  };
}

function sampleRectSurface(
  random: SeededRandom,
  minX: number,
  maxX: number,
  minY: number,
  maxY: number,
  z: number,
): Vec3 {
  return {
    x: random.range(minX, maxX),
    y: random.range(minY, maxY),
    z: z + random.signed() * random.range(0, 3.6),
  };
}

function sampleBuilding(random: SeededRandom): LayerWriter {
  const z = 625;
  const roll = random.next();
  let point: Vec3;
  let edge = 0;

  if (roll < 0.24) {
    point = sampleRectSurface(random, -116, 116, 8, 66, z);
    const doorway = Math.abs(point.x) < 28 && point.y < 48;
    if (doorway) {
      point.x += point.x < 0 ? -36 : 36;
      point.y += random.range(8, 18);
    }
    edge = 0.08;
  } else if (roll < 0.42) {
    const roofX = random.range(-140, 140);
    const roofY = 66 + (1 - Math.abs(roofX) / 140) * 30;
    point = { x: roofX, y: roofY + random.signed() * 2.6, z: z - random.range(0, 7) };
    edge = 0.6;
  } else if (roll < 0.62) {
    const columns = [-82, -52, 52, 82];
    const column = columns[Math.floor(random.next() * columns.length)];
    point = {
      x: column + random.signed() * random.range(0, 4.8),
      y: random.range(6, 66),
      z: z - random.range(0, 8),
    };
    edge = 0.56;
  } else if (roll < 0.78) {
    const y = random.next() < 0.5 ? random.range(6, 12) : random.range(56, 66);
    point = { x: random.range(-118, 118), y, z: z - random.range(0, 6) };
    edge = 0.48;
  } else if (roll < 0.9) {
    const side = random.next() < 0.5 ? -1 : 1;
    point = {
      x: side * random.range(118, 136),
      y: random.range(8, 74),
      z: z - random.range(0, 5),
    };
    edge = 0.46;
  } else {
    const side = random.next() < 0.5 ? -1 : 1;
    point = {
      x: side * random.range(34, 104) + random.signed() * random.range(0, 4),
      y: random.range(26, 48) + random.signed() * random.range(0, 5),
      z: z - random.range(0, 5),
    };
    edge = 0.36;
  }

  const pathGlow = gaussian(point.x - pathCenterX(point.z), 72) * gaussian(point.y - 8, 26);

  return {
    ...point,
    color: facadeColor(random, edge + pathGlow * 0.24),
    size: random.next() > 0.88 ? random.range(0.9, 2.7) : random.range(0.28, 1.14),
    alpha: random.range(0.08, 0.32) * (0.82 + edge * 0.18),
    random: random.next(),
  };
}

export function gardenGrassPointCloud(count: number): GeneratedPointCloudLayer {
  return createLayer("foregroundGroundPointCloud", count, 7103, random => {
    const point = sampleGround(random);
    const pathMask = gaussian(point.x - pathCenterX(point.z), pathWidth(point.z) * 0.88);

    return {
      ...point,
      color: groundColor(random, point.x, point.z),
      size: sizeByDepth(random, point.z, 0.34, 4.7),
      alpha: random.range(0.26, 0.7) * (1 - pathMask * 0.42),
      random: random.next(),
    };
  });
}

export function gardenFlowerBandPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("midGroundMistPointCloud", count, 7207, random => sampleFlower(random));
}

export function gardenHorizonPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("horizonGlowBandPointCloud", count, 7301, random => samplePath(random));
}

export function gardenSideTreeWallPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("sideBoundaryPointCloud", count, 7351, random => {
    const side = random.next() < 0.5 ? -1 : 1;
    const z = random.range(250, 760);
    const wallInner = 150 + z * 0.12;
    const wallDepth = random.range(0, 280) * Math.pow(random.next(), 0.58);
    const x =
      pathCenterX(z) +
      side * (wallInner + wallDepth) +
      Math.sin(z * 0.019 + side * 0.7) * random.range(4, 38);
    const ground = groundY(x, z);
    const canopyBand = random.next() < 0.76;
    const y = canopyBand
      ? ground + random.range(42, 218) * Math.pow(random.next(), 0.7)
      : ground + random.range(4, 62) * Math.pow(random.next(), 0.54);
    const sideGlow = smoothstep(190, 610, Math.abs(x));
    const upperGlow = smoothstep(12, 190, y - ground);
    const centerOpening = gaussian(x, 122) * gaussian(z - 600, 120);

    return {
      x,
      y,
      z: z + random.signed() * random.range(0, 34),
      color: treeColor(random, sideGlow * 0.16 + upperGlow * 0.26),
      size: sizeByDepth(random, z, 0.26, 2.5) + upperGlow * random.range(0, 0.46),
      alpha: random.range(0.12, 0.44) * (1 - centerOpening * 0.42),
      random: random.next(),
    };
  });
}

export function gardenAirPointCloud(count: number): GeneratedPointCloudLayer {
  return createLayer("ambientDeepSpacePointCloud", count, 7409, random => {
    const z = random.range(250, 850);
    const x = random.signed() * random.range(120, 720);
    const y = random.range(20, 190);
    const horizon = 1 - smoothstep(46, 190, y);

    return {
      x,
      y,
      z,
      color: mixColor(airBlue, treeMist, random.range(0.02, 0.2)),
      size: random.range(0.18, 0.92),
      alpha: random.range(0.012, 0.056) * (0.58 + horizon * 0.36),
      random: random.next(),
    };
  });
}

export function gardenDistantEnvironmentPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("distantEnvironmentPointCloud", count, 7417, random => sampleTreeOrShrub(random));
}

export function gardenDistantPalacePointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("distantPalacePointCloud", count, 7523, random => sampleBuilding(random));
}

export function gardenTransitionPointCloud(
  count: number,
): GeneratedPointCloudLayer {
  return createLayer("transitionDensePointCloud", count, 7617, random => {
    const angle = random.range(0, Math.PI * 2);
    const radius = random.range(18, 180) * Math.pow(random.next(), 0.36);
    const z = random.range(42, 275);
    const x = Math.cos(angle) * radius + Math.sin(z * 0.026) * 16;
    const y = -7 + Math.sin(angle) * radius * 0.28 + random.signed() * 18;
    const tunnel = gaussian(radius - 82, 52);
    const color = random.next() < 0.72
      ? mixColor(grassGreen, tenderGreen, random.range(0.16, 0.74))
      : flowerColor(random, tunnel);

    return {
      x,
      y,
      z,
      color,
      size: random.range(0.42, 2.8),
      alpha: random.range(0.07, 0.22) * (0.68 + tunnel * 0.36),
      random: random.next(),
    };
  });
}

export function fallbackFocusParticle(): GeneratedPointCloudLayer {
  return createLayer("focusParticle", 1, 7701, () => ({
    x: pathCenterX(608),
    y: 10,
    z: 608,
    color: warmSignal,
    size: 5.2,
    alpha: 0.72,
    random: 0.42,
  }));
}

export function generateFallbackPointCloudLayers(
  counts: LayerCounts,
): GeneratedPointCloudLayer[] {
  return [
    gardenGrassPointCloud(counts.foregroundGroundPointCloud),
    gardenFlowerBandPointCloud(counts.midGroundMistPointCloud),
    gardenHorizonPointCloud(counts.horizonGlowBandPointCloud),
    gardenSideTreeWallPointCloud(counts.sideBoundaryPointCloud),
    gardenDistantEnvironmentPointCloud(counts.distantEnvironmentPointCloud),
    gardenDistantPalacePointCloud(counts.distantPalacePointCloud),
    gardenAirPointCloud(counts.ambientDeepSpacePointCloud),
    gardenTransitionPointCloud(counts.transitionDensePointCloud),
    fallbackFocusParticle(),
  ];
}
