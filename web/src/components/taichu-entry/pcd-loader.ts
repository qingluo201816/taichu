import type {
  GeneratedPointCloudLayer,
  PerformanceTier,
  PointCloudLayerName,
} from "./types";

type PcdDataType = "ascii" | "binary";
type PcdScalarType = "F" | "I" | "U";

type PcdFieldLayout = {
  tokenOffset: number;
  byteOffset: number;
  size: number;
  type: PcdScalarType;
};

type PcdHeader = {
  fields: string[];
  sizes: number[];
  types: PcdScalarType[];
  counts: number[];
  points: number;
  dataType: PcdDataType;
  dataOffset: number;
  stride: number;
  fieldLayouts: Map<string, PcdFieldLayout>;
};

type LoadPcdOptions = {
  tier: PerformanceTier;
  reducedMotion: boolean;
};

type Bounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
};

const layerId: Record<PointCloudLayerName, number> = {
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

const targetPointBudget: Record<PerformanceTier, number> = {
  high: 150000,
  medium: 90000,
  low: 55000,
};

type DecompressionStreamConstructor = new (
  format: "gzip",
) => TransformStream<Uint8Array, Uint8Array>;

function isGzipUrl(url: string): boolean {
  return url.toLowerCase().endsWith(".gz");
}

async function fetchPointCloudBuffer(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("点云资产读取失败");
  }

  const buffer = await response.arrayBuffer();
  if (!isGzipUrl(url)) {
    return buffer;
  }

  const DecompressionStreamCtor = (
    globalThis as typeof globalThis & {
      DecompressionStream?: DecompressionStreamConstructor;
    }
  ).DecompressionStream;

  if (!DecompressionStreamCtor) {
    throw new Error("当前浏览器不支持 gzip 点云解压");
  }

  const stream = new Blob([buffer])
    .stream()
    .pipeThrough(new DecompressionStreamCtor("gzip"));
  return new Response(stream).arrayBuffer();
}

function decodeAscii(bytes: Uint8Array): string {
  return new TextDecoder("ascii").decode(bytes);
}

function findHeader(bytes: Uint8Array): { dataOffset: number; dataType: PcdDataType } {
  let lineStart = 0;

  for (let index = 0; index < bytes.length; index += 1) {
    if (bytes[index] !== 10) {
      continue;
    }

    const line = decodeAscii(bytes.slice(lineStart, index)).trim();
    const parts = line.split(/\s+/);
    if (parts[0]?.toUpperCase() === "DATA") {
      if (parts[1] !== "ascii" && parts[1] !== "binary") {
        throw new Error("入口点云暂不支持该 PCD DATA 类型");
      }
      return { dataOffset: index + 1, dataType: parts[1] };
    }

    lineStart = index + 1;
  }

  throw new Error("点云文件缺少 PCD DATA 头信息");
}

function parseHeader(bytes: Uint8Array): PcdHeader {
  const { dataOffset, dataType } = findHeader(bytes);
  const lines = decodeAscii(bytes.slice(0, dataOffset)).split(/\r?\n/);
  let fields: string[] = [];
  let sizes: number[] = [];
  let types: PcdScalarType[] = [];
  let counts: number[] = [];
  let points = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const parts = trimmed.split(/\s+/);
    const key = parts[0].toUpperCase();
    if (key === "FIELDS") {
      fields = parts.slice(1);
    } else if (key === "SIZE") {
      sizes = parts.slice(1).map(Number);
    } else if (key === "TYPE") {
      types = parts.slice(1) as PcdScalarType[];
    } else if (key === "COUNT") {
      counts = parts.slice(1).map(Number);
    } else if (key === "POINTS") {
      points = Number(parts[1]);
    } else if (key === "WIDTH" && !points) {
      points = Number(parts[1]);
    }
  }

  if (!fields.length || !sizes.length || !types.length || !points) {
    throw new Error("点云文件缺少 PCD 字段声明");
  }

  if (!counts.length) {
    counts = fields.map(() => 1);
  }

  let byteOffset = 0;
  let tokenOffset = 0;
  const fieldLayouts = new Map<string, PcdFieldLayout>();
  for (let index = 0; index < fields.length; index += 1) {
    const count = counts[index] ?? 1;
    const size = sizes[index];
    const type = types[index];
    if (type !== "F" && type !== "I" && type !== "U") {
      throw new Error("入口点云存在未知 PCD 字段类型");
    }
    fieldLayouts.set(fields[index], {
      tokenOffset,
      byteOffset,
      size,
      type,
    });
    tokenOffset += count;
    byteOffset += size * count;
  }

  return {
    fields,
    sizes,
    types,
    counts,
    points,
    dataType,
    dataOffset,
    stride: byteOffset,
    fieldLayouts,
  };
}

function readBinaryScalar(
  view: DataView,
  offset: number,
  size: number,
  type: PcdScalarType,
): number {
  if (type === "F") {
    return size === 8 ? view.getFloat64(offset, true) : view.getFloat32(offset, true);
  }

  if (type === "I") {
    if (size === 1) {
      return view.getInt8(offset);
    }
    if (size === 2) {
      return view.getInt16(offset, true);
    }
    return view.getInt32(offset, true);
  }

  if (size === 1) {
    return view.getUint8(offset);
  }
  if (size === 2) {
    return view.getUint16(offset, true);
  }
  return view.getUint32(offset, true);
}

function createEmptyBounds(): Bounds {
  return {
    minX: Number.POSITIVE_INFINITY,
    maxX: Number.NEGATIVE_INFINITY,
    minY: Number.POSITIVE_INFINITY,
    maxY: Number.NEGATIVE_INFINITY,
    minZ: Number.POSITIVE_INFINITY,
    maxZ: Number.NEGATIVE_INFINITY,
  };
}

function expandBounds(bounds: Bounds, x: number, y: number, z: number): void {
  bounds.minX = Math.min(bounds.minX, x);
  bounds.maxX = Math.max(bounds.maxX, x);
  bounds.minY = Math.min(bounds.minY, y);
  bounds.maxY = Math.max(bounds.maxY, y);
  bounds.minZ = Math.min(bounds.minZ, z);
  bounds.maxZ = Math.max(bounds.maxZ, z);
}

function sampleCountFor(
  pointCount: number,
  tier: PerformanceTier,
  reducedMotion: boolean,
): number {
  const budget = reducedMotion
    ? Math.min(targetPointBudget[tier], 42000)
    : targetPointBudget[tier];
  return Math.min(pointCount, budget);
}

function hash01(value: number): number {
  let seed = (value + 1) * 2654435761;
  seed ^= seed >>> 16;
  seed = Math.imul(seed, 2246822507);
  seed ^= seed >>> 13;
  seed = Math.imul(seed, 3266489909);
  seed ^= seed >>> 16;
  return (seed >>> 0) / 4294967296;
}

function normalizedColor(channel: number): number {
  return Math.min(1, Math.max(0, 0.14 + channel * 1.22));
}

function unpackRgb(value: number): [number, number, number] {
  const packed = value >>> 0;
  return [
    ((packed >> 16) & 255) / 255,
    ((packed >> 8) & 255) / 255,
    (packed & 255) / 255,
  ];
}

function unpackRgbFromFloat(value: number): [number, number, number] {
  const buffer = new ArrayBuffer(4);
  const view = new DataView(buffer);
  view.setFloat32(0, value, true);
  return unpackRgb(view.getUint32(0, true));
}

function asciiPoint(
  tokens: string[],
  header: PcdHeader,
): { x: number; y: number; z: number; red: number; green: number; blue: number } {
  const read = (name: string, fallback: number): number => {
    const layout = header.fieldLayouts.get(name);
    if (!layout) {
      return fallback;
    }
    return Number(tokens[layout.tokenOffset] ?? fallback);
  };
  const rgbLayout = header.fieldLayouts.get("rgb") ?? header.fieldLayouts.get("rgba");
  let rgb: [number, number, number] | null = null;
  if (rgbLayout) {
    const value = Number(tokens[rgbLayout.tokenOffset] ?? 0);
    rgb = rgbLayout.type === "F" ? unpackRgbFromFloat(value) : unpackRgb(value);
  }

  return {
    x: read("x", 0),
    y: read("y", 0),
    z: read("z", 0),
    red: rgb?.[0] ?? read("r", read("red", 184)) / 255,
    green: rgb?.[1] ?? read("g", read("green", 168)) / 255,
    blue: rgb?.[2] ?? read("b", read("blue", 138)) / 255,
  };
}

function binaryPoint(
  view: DataView,
  baseOffset: number,
  header: PcdHeader,
): { x: number; y: number; z: number; red: number; green: number; blue: number } {
  const read = (name: string, fallback: number): number => {
    const layout = header.fieldLayouts.get(name);
    if (!layout) {
      return fallback;
    }
    return readBinaryScalar(
      view,
      baseOffset + layout.byteOffset,
      layout.size,
      layout.type,
    );
  };
  const rgbLayout = header.fieldLayouts.get("rgb") ?? header.fieldLayouts.get("rgba");
  let rgb: [number, number, number] | null = null;
  if (rgbLayout) {
    const value = readBinaryScalar(
      view,
      baseOffset + rgbLayout.byteOffset,
      rgbLayout.size,
      rgbLayout.type,
    );
    rgb = rgbLayout.type === "F" ? unpackRgbFromFloat(value) : unpackRgb(value);
  }

  return {
    x: read("x", 0),
    y: read("y", 0),
    z: read("z", 0),
    red: rgb?.[0] ?? read("r", read("red", 184)) / 255,
    green: rgb?.[1] ?? read("g", read("green", 168)) / 255,
    blue: rgb?.[2] ?? read("b", read("blue", 138)) / 255,
  };
}

export async function loadPcdPointCloudLayer(
  url: string,
  options: LoadPcdOptions,
): Promise<GeneratedPointCloudLayer> {
  const buffer = await fetchPointCloudBuffer(url);
  const bytes = new Uint8Array(buffer);
  const header = parseHeader(bytes);
  const view = new DataView(buffer);
  const asciiRows = header.dataType === "ascii"
    ? decodeAscii(bytes.slice(header.dataOffset)).trim().split(/\r?\n/)
    : [];
  const pointAt = (index: number) => {
    if (header.dataType === "ascii") {
      return asciiPoint(asciiRows[index].trim().split(/\s+/), header);
    }
    return binaryPoint(view, header.dataOffset + index * header.stride, header);
  };

  if (
    !header.fieldLayouts.has("x") ||
    !header.fieldLayouts.has("y") ||
    !header.fieldLayouts.has("z")
  ) {
    throw new Error("点云文件缺少 x/y/z 坐标");
  }

  const bounds = createEmptyBounds();
  for (let index = 0; index < header.points; index += 1) {
    const point = pointAt(index);
    expandBounds(bounds, point.x, point.y, point.z);
  }

  const count = sampleCountFor(header.points, options.tier, options.reducedMotion);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);
  const alphas = new Float32Array(count);
  const randoms = new Float32Array(count);
  const amplitudes = new Float32Array(count);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const spanX = Math.max(0.0001, bounds.maxX - bounds.minX);
  const spanY = Math.max(0.0001, bounds.maxY - bounds.minY);
  const spanZ = Math.max(0.0001, bounds.maxZ - bounds.minZ);
  const scale = 620 / Math.max(spanX, spanZ, spanY * 2.2);

  for (let index = 0; index < count; index += 1) {
    const sourceIndex =
      count === header.points
        ? index
        : Math.floor((index / count) * header.points);
    const point = pointAt(sourceIndex);
    const luminance = point.red * 0.2126 + point.green * 0.7152 + point.blue * 0.0722;
    const depth = (point.z - bounds.minZ) / spanZ;
    const random = hash01(sourceIndex);
    const positionOffset = index * 3;

    positions[positionOffset] = (point.x - centerX) * scale;
    positions[positionOffset + 1] = (point.y - centerY) * scale - 42;
    positions[positionOffset + 2] = depth * spanZ * scale + 44;
    colors[positionOffset] = normalizedColor(point.red);
    colors[positionOffset + 1] = normalizedColor(point.green);
    colors[positionOffset + 2] = normalizedColor(point.blue);
    sizes[index] = 0.56 + Math.pow(luminance, 0.82) * 2.6 + random * 0.36;
    alphas[index] = 0.16 + Math.pow(luminance, 0.72) * 0.62;
    randoms[index] = random;
    amplitudes[index] = Math.min(
      1,
      Math.max(0.05, 0.16 + luminance * 0.72 + depth * 0.18 + random * 0.12),
    );
  }

  return {
    name: "sourcePointCloud",
    layerId: layerId.sourcePointCloud,
    count,
    positions,
    colors,
    sizes,
    alphas,
    randoms,
    amplitudes,
  };
}
