import type {
  GeneratedGaussianSplatLayer,
  GeneratedPointCloudLayer,
  LoadedPointCloudAsset,
  PerformanceTier,
  PointCloudAssetRenderMode,
  PointCloudLayerName,
} from "./types";

type PlyScalarType =
  | "char"
  | "uchar"
  | "short"
  | "ushort"
  | "int"
  | "uint"
  | "float"
  | "double";

type PlyProperty = {
  name: string;
  type: PlyScalarType;
  offset: number;
};

type Bounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
};

type PlyHeader = {
  vertexCount: number;
  properties: PlyProperty[];
  stride: number;
  dataOffset: number;
};

type LoadPlyOptions = {
  tier: PerformanceTier;
  reducedMotion: boolean;
  renderMode?: PointCloudAssetRenderMode;
};

const encoder = new TextEncoder();

const propertySize: Record<PlyScalarType, number> = {
  char: 1,
  uchar: 1,
  short: 2,
  ushort: 2,
  int: 4,
  uint: 4,
  float: 4,
  double: 8,
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

const targetSplatBudget: Record<PerformanceTier, number> = {
  high: Number.POSITIVE_INFINITY,
  medium: 260000,
  low: 90000,
};

const targetDetailPointBudget: Record<PerformanceTier, number> = {
  high: 56000,
  medium: 36000,
  low: 18000,
};

const targetVolumePointBudget: Record<PerformanceTier, number> = {
  high: 92000,
  medium: 56000,
  low: 28000,
};

const sphericalHarmonicC0 = 0.28209479177387814;

function readScalar(
  view: DataView,
  offset: number,
  type: PlyScalarType,
): number {
  switch (type) {
    case "char":
      return view.getInt8(offset);
    case "uchar":
      return view.getUint8(offset);
    case "short":
      return view.getInt16(offset, true);
    case "ushort":
      return view.getUint16(offset, true);
    case "int":
      return view.getInt32(offset, true);
    case "uint":
      return view.getUint32(offset, true);
    case "float":
      return view.getFloat32(offset, true);
    case "double":
      return view.getFloat64(offset, true);
  }
}

function findHeaderEnd(bytes: Uint8Array): number {
  const lfMarker = encoder.encode("end_header\n");
  const crlfMarker = encoder.encode("end_header\r\n");
  const maxStart = bytes.length - lfMarker.length;

  for (let index = 0; index <= maxStart; index += 1) {
    if (matchesAt(bytes, lfMarker, index)) {
      return index + lfMarker.length;
    }
    if (matchesAt(bytes, crlfMarker, index)) {
      return index + crlfMarker.length;
    }
  }

  throw new Error("点云文件缺少 PLY 头信息");
}

function matchesAt(
  bytes: Uint8Array,
  marker: Uint8Array,
  start: number,
): boolean {
  if (start + marker.length > bytes.length) {
    return false;
  }

  for (let index = 0; index < marker.length; index += 1) {
    if (bytes[start + index] !== marker[index]) {
      return false;
    }
  }

  return true;
}

function parseHeader(bytes: Uint8Array): PlyHeader {
  const dataOffset = findHeaderEnd(bytes);
  const headerText = new TextDecoder("ascii").decode(bytes.slice(0, dataOffset));
  const lines = headerText.split(/\r?\n/);
  let vertexCount = 0;
  let inVertex = false;
  let offset = 0;
  const properties: PlyProperty[] = [];

  for (const line of lines) {
    const parts = line.trim().split(/\s+/);

    if (parts[0] === "format" && parts[1] !== "binary_little_endian") {
      throw new Error("当前入口只支持 binary little-endian PLY 点云");
    }

    if (parts[0] === "element") {
      inVertex = parts[1] === "vertex";
      if (inVertex) {
        vertexCount = Number(parts[2]);
      }
      continue;
    }

    if (inVertex && parts[0] === "property") {
      if (parts[1] === "list") {
        throw new Error("入口点云暂不支持 vertex list 属性");
      }

      const type = parts[1] as PlyScalarType;
      if (!(type in propertySize)) {
        throw new Error(`入口点云存在未知属性类型：${parts[1]}`);
      }

      properties.push({ name: parts[2], type, offset });
      offset += propertySize[type];
    }
  }

  if (!vertexCount || properties.length === 0) {
    throw new Error("点云文件没有可读取的顶点数据");
  }

  return { vertexCount, properties, stride: offset, dataOffset };
}

function propertyMap(properties: PlyProperty[]): Map<string, PlyProperty> {
  return new Map(properties.map(property => [property.name, property]));
}

function readProperty(
  view: DataView,
  baseOffset: number,
  property: PlyProperty | undefined,
  fallback: number,
): number {
  if (!property) {
    return fallback;
  }

  return readScalar(view, baseOffset + property.offset, property.type);
}

function colorChannel(
  view: DataView,
  baseOffset: number,
  property: PlyProperty | undefined,
  fallback: number,
): number {
  const value = readProperty(view, baseOffset, property, fallback);
  return Math.max(0, Math.min(255, value)) / 255;
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

function sampleCountFor(
  vertexCount: number,
  tier: PerformanceTier,
  reducedMotion: boolean,
): number {
  const budget = reducedMotion
    ? Math.min(targetPointBudget[tier], 42000)
    : targetPointBudget[tier];
  return Math.min(vertexCount, budget);
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

function normalizedColor(channel: number): number {
  return Math.min(1, Math.max(0, 0.14 + channel * 1.22));
}

function sigmoid(value: number): number {
  return 1 / (1 + Math.exp(-value));
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function hasGaussianSplatFields(properties: Map<string, PlyProperty>): boolean {
  return (
    properties.has("f_dc_0") &&
    properties.has("f_dc_1") &&
    properties.has("f_dc_2") &&
    properties.has("opacity") &&
    properties.has("scale_0") &&
    properties.has("scale_1") &&
    properties.has("scale_2") &&
    properties.has("rot_0") &&
    properties.has("rot_1") &&
    properties.has("rot_2") &&
    properties.has("rot_3")
  );
}

function sampleSplatCountFor(
  vertexCount: number,
  tier: PerformanceTier,
  reducedMotion: boolean,
): number {
  const budget = reducedMotion
    ? Math.min(targetSplatBudget[tier], 55000)
    : targetSplatBudget[tier];
  return Math.min(vertexCount, budget);
}

function sampleDetailPointCountFor(
  vertexCount: number,
  tier: PerformanceTier,
  reducedMotion: boolean,
): number {
  const budget = reducedMotion
    ? Math.min(targetDetailPointBudget[tier], 14000)
    : targetDetailPointBudget[tier];
  return Math.min(vertexCount, budget);
}

function sampleVolumePointCountFor(
  vertexCount: number,
  tier: PerformanceTier,
  reducedMotion: boolean,
): number {
  const budget = reducedMotion
    ? Math.min(targetVolumePointBudget[tier], 16000)
    : targetVolumePointBudget[tier];
  return Math.min(vertexCount, budget);
}

function normalizeQuaternion(
  w: number,
  x: number,
  y: number,
  z: number,
): [number, number, number, number] {
  const length = Math.max(0.000001, Math.hypot(w, x, y, z));
  return [w / length, x / length, y / length, z / length];
}

function gaussianSplatColor(
  f0: number,
  f1: number,
  f2: number,
): [number, number, number] {
  return [
    clamp01(0.5 + sphericalHarmonicC0 * f0),
    clamp01(0.5 + sphericalHarmonicC0 * f1),
    clamp01(0.5 + sphericalHarmonicC0 * f2),
  ];
}

function visualGaussianSplatScale(scale: number): number {
  return Math.min(1.62, Math.max(0.04, scale * 0.66));
}

function visualGaussianSplatAlpha(alpha: number, luminance: number): number {
  const darkDetailFade = 0.36 + Math.pow(luminance, 0.72) * 0.66;
  return Math.min(0.78, Math.pow(alpha, 1.18) * darkDetailFade);
}

function visualGaussianSplatColor(
  color: [number, number, number],
): [number, number, number] {
  return [
    clamp01(Math.pow(color[0], 0.82) * 1.16 + 0.034),
    clamp01(Math.pow(color[1], 0.82) * 1.12 + 0.028),
    clamp01(Math.pow(color[2], 0.84) * 1.24 + 0.038),
  ];
}

export async function loadPlyPointCloudLayer(
  url: string,
  options: LoadPlyOptions,
): Promise<GeneratedPointCloudLayer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("点云资产读取失败");
  }

  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const header = parseHeader(bytes);
  const view = new DataView(buffer);
  const properties = propertyMap(header.properties);
  const xProperty = properties.get("x");
  const yProperty = properties.get("y");
  const zProperty = properties.get("z");
  const redProperty = properties.get("red") ?? properties.get("r");
  const greenProperty = properties.get("green") ?? properties.get("g");
  const blueProperty = properties.get("blue") ?? properties.get("b");

  if (!xProperty || !yProperty || !zProperty) {
    throw new Error("点云文件缺少 x/y/z 坐标");
  }

  const bounds = createEmptyBounds();
  for (let index = 0; index < header.vertexCount; index += 1) {
    const offset = header.dataOffset + index * header.stride;
    expandBounds(
      bounds,
      readProperty(view, offset, xProperty, 0),
      readProperty(view, offset, yProperty, 0),
      readProperty(view, offset, zProperty, 0),
    );
  }

  const count = sampleCountFor(
    header.vertexCount,
    options.tier,
    options.reducedMotion,
  );
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
      count === header.vertexCount
        ? index
        : Math.floor((index / count) * header.vertexCount);
    const offset = header.dataOffset + sourceIndex * header.stride;
    const x = readProperty(view, offset, xProperty, 0);
    const y = readProperty(view, offset, yProperty, 0);
    const z = readProperty(view, offset, zProperty, 0);
    const red = colorChannel(view, offset, redProperty, 0.72);
    const green = colorChannel(view, offset, greenProperty, 0.66);
    const blue = colorChannel(view, offset, blueProperty, 0.54);
    const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722;
    const depth = (z - bounds.minZ) / spanZ;
    const random = hash01(sourceIndex);
    const positionOffset = index * 3;

    positions[positionOffset] = (x - centerX) * scale;
    positions[positionOffset + 1] = (y - centerY) * scale - 42;
    positions[positionOffset + 2] = depth * spanZ * scale + 44;
    colors[positionOffset] = normalizedColor(red);
    colors[positionOffset + 1] = normalizedColor(green);
    colors[positionOffset + 2] = normalizedColor(blue);
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

export async function loadPlyAsset(
  url: string,
  options: LoadPlyOptions,
): Promise<LoadedPointCloudAsset> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("点云资产读取失败");
  }

  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const header = parseHeader(bytes);
  const view = new DataView(buffer);
  const properties = propertyMap(header.properties);
  const shouldUseGaussianSplat =
    options.renderMode === "gaussian-splat" ||
    (options.renderMode !== "point-cloud" && hasGaussianSplatFields(properties));

  if (!shouldUseGaussianSplat) {
    return {
      kind: "point-cloud",
      layer: await loadPlyPointCloudLayer(url, options),
    };
  }

  return {
    kind: "gaussian-splat",
    layer: loadGaussianSplatLayerFromBuffer(view, header, properties, options),
    volumeLayers: loadGaussianSplatVolumeLayersFromBuffer(
      view,
      header,
      properties,
      options,
    ),
    detailLayer: loadGaussianSplatDetailLayerFromBuffer(
      view,
      header,
      properties,
      options,
    ),
  };
}

function loadGaussianSplatLayerFromBuffer(
  view: DataView,
  header: PlyHeader,
  properties: Map<string, PlyProperty>,
  options: LoadPlyOptions,
): GeneratedGaussianSplatLayer {
  const xProperty = properties.get("x");
  const yProperty = properties.get("y");
  const zProperty = properties.get("z");
  const f0Property = properties.get("f_dc_0");
  const f1Property = properties.get("f_dc_1");
  const f2Property = properties.get("f_dc_2");
  const opacityProperty = properties.get("opacity");
  const scale0Property = properties.get("scale_0");
  const scale1Property = properties.get("scale_1");
  const scale2Property = properties.get("scale_2");
  const rot0Property = properties.get("rot_0");
  const rot1Property = properties.get("rot_1");
  const rot2Property = properties.get("rot_2");
  const rot3Property = properties.get("rot_3");

  if (
    !xProperty ||
    !yProperty ||
    !zProperty ||
    !f0Property ||
    !f1Property ||
    !f2Property ||
    !opacityProperty ||
    !scale0Property ||
    !scale1Property ||
    !scale2Property ||
    !rot0Property ||
    !rot1Property ||
    !rot2Property ||
    !rot3Property
  ) {
    throw new Error("Gaussian Splat 点云缺少必要字段");
  }

  const bounds = createEmptyBounds();
  for (let index = 0; index < header.vertexCount; index += 1) {
    const offset = header.dataOffset + index * header.stride;
    expandBounds(
      bounds,
      readProperty(view, offset, xProperty, 0),
      readProperty(view, offset, yProperty, 0),
      readProperty(view, offset, zProperty, 0),
    );
  }

  const count = sampleSplatCountFor(
    header.vertexCount,
    options.tier,
    options.reducedMotion,
  );
  const centers = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const alphas = new Float32Array(count);
  const scales = new Float32Array(count * 3);
  const rotations = new Float32Array(count * 4);
  const randoms = new Float32Array(count);
  const amplitudes = new Float32Array(count);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  const spanX = Math.max(0.0001, bounds.maxX - bounds.minX);
  const spanY = Math.max(0.0001, bounds.maxY - bounds.minY);
  const spanZ = Math.max(0.0001, bounds.maxZ - bounds.minZ);
  const sceneScale = 620 / Math.max(spanX, spanZ, spanY * 2.2);
  const sourceIndices = new Uint32Array(count);
  const sourceDepths = new Float32Array(count);
  const renderOrder = Array.from({ length: count }, (_, index) => index);

  for (let index = 0; index < count; index += 1) {
    const sourceIndex =
      count === header.vertexCount
        ? index
        : Math.floor((index / count) * header.vertexCount);
    const sourceOffset = header.dataOffset + sourceIndex * header.stride;
    sourceIndices[index] = sourceIndex;
    sourceDepths[index] = readProperty(view, sourceOffset, zProperty, 0);
  }

  renderOrder.sort((left, right) => sourceDepths[right] - sourceDepths[left]);

  for (let index = 0; index < count; index += 1) {
    const sampleIndex = renderOrder[index];
    const sourceIndex = sourceIndices[sampleIndex];
    const sourceOffset = header.dataOffset + sourceIndex * header.stride;
    const x = readProperty(view, sourceOffset, xProperty, 0);
    const y = readProperty(view, sourceOffset, yProperty, 0);
    const z = readProperty(view, sourceOffset, zProperty, 0);
    const f0 = readProperty(view, sourceOffset, f0Property, 0);
    const f1 = readProperty(view, sourceOffset, f1Property, 0);
    const f2 = readProperty(view, sourceOffset, f2Property, 0);
    const rawColor = gaussianSplatColor(f0, f1, f2);
    const alpha = sigmoid(readProperty(view, sourceOffset, opacityProperty, 0));
    const rotation = normalizeQuaternion(
      readProperty(view, sourceOffset, rot0Property, 1),
      readProperty(view, sourceOffset, rot1Property, 0),
      readProperty(view, sourceOffset, rot2Property, 0),
      readProperty(view, sourceOffset, rot3Property, 0),
    );
    const depth = (z - bounds.minZ) / spanZ;
    const random = hash01(sourceIndex);
    const centerOffset = index * 3;
    const rotationOffset = index * 4;
    const luminance = rawColor[0] * 0.2126 + rawColor[1] * 0.7152 + rawColor[2] * 0.0722;
    const color = visualGaussianSplatColor(rawColor);
    const baseScale0 = Math.exp(readProperty(view, sourceOffset, scale0Property, -4.5));
    const baseScale1 = Math.exp(readProperty(view, sourceOffset, scale1Property, -4.5));
    const baseScale2 = Math.exp(readProperty(view, sourceOffset, scale2Property, -4.5));

    centers[centerOffset] = (x - centerX) * sceneScale;
    centers[centerOffset + 1] = (y - centerY) * sceneScale - 42;
    centers[centerOffset + 2] = depth * spanZ * sceneScale + 44;
    colors[centerOffset] = color[0];
    colors[centerOffset + 1] = color[1];
    colors[centerOffset + 2] = color[2];
    alphas[index] = visualGaussianSplatAlpha(alpha, luminance);
    scales[centerOffset] = visualGaussianSplatScale(baseScale0 * sceneScale);
    scales[centerOffset + 1] = visualGaussianSplatScale(baseScale1 * sceneScale);
    scales[centerOffset + 2] = visualGaussianSplatScale(baseScale2 * sceneScale);
    rotations[rotationOffset] = rotation[0];
    rotations[rotationOffset + 1] = rotation[1];
    rotations[rotationOffset + 2] = rotation[2];
    rotations[rotationOffset + 3] = rotation[3];
    randoms[index] = random;
    amplitudes[index] = Math.min(
      1,
      Math.max(0.06, alpha * 0.48 + luminance * 0.36 + depth * 0.1 + random * 0.06),
    );
  }

  return {
    name: "sourcePointCloud",
    count,
    centers,
    colors,
    alphas,
    scales,
    rotations,
    randoms,
    amplitudes,
  };
}

function loadGaussianSplatVolumeLayersFromBuffer(
  view: DataView,
  header: PlyHeader,
  properties: Map<string, PlyProperty>,
  options: LoadPlyOptions,
): GeneratedPointCloudLayer[] {
  const xProperty = properties.get("x");
  const yProperty = properties.get("y");
  const zProperty = properties.get("z");
  const f0Property = properties.get("f_dc_0");
  const f1Property = properties.get("f_dc_1");
  const f2Property = properties.get("f_dc_2");
  const opacityProperty = properties.get("opacity");

  if (
    !xProperty ||
    !yProperty ||
    !zProperty ||
    !f0Property ||
    !f1Property ||
    !f2Property ||
    !opacityProperty
  ) {
    throw new Error("Gaussian Splat 点云缺少内部星尘字段");
  }

  const bounds = createEmptyBounds();
  for (let index = 0; index < header.vertexCount; index += 1) {
    const offset = header.dataOffset + index * header.stride;
    expandBounds(
      bounds,
      readProperty(view, offset, xProperty, 0),
      readProperty(view, offset, yProperty, 0),
      readProperty(view, offset, zProperty, 0),
    );
  }

  const totalCount = sampleVolumePointCountFor(
    header.vertexCount,
    options.tier,
    options.reducedMotion,
  );
  const spanX = Math.max(0.0001, bounds.maxX - bounds.minX);
  const spanY = Math.max(0.0001, bounds.maxY - bounds.minY);
  const spanZ = Math.max(0.0001, bounds.maxZ - bounds.minZ);
  const sceneScale = 620 / Math.max(spanX, spanZ, spanY * 2.2);
  const radiusX = spanX * sceneScale * 0.42;
  const radiusY = spanY * sceneScale * 0.35;
  const radiusZ = spanZ * sceneScale * 0.45;
  const worldCenterY = -42;
  const worldCenterZ = spanZ * sceneScale * 0.5 + 44;
  const foregroundCount = Math.max(0, Math.floor(totalCount * 0.08));
  const midCount = Math.max(0, Math.floor(totalCount * 0.5));
  const farCount = Math.max(0, totalCount - foregroundCount - midCount);

  return [
    createGaussianSplatVolumeLayer({
      name: "foregroundGroundPointCloud",
      count: foregroundCount,
      seedOffset: 101,
      radiusMin: 0.08,
      radiusMax: 0.54,
      radiusExponent: 1.55,
      verticalScale: 0.72,
      zBias: -10,
      swirlStrength: 2.25,
      bandFrequency: 3.7,
      baseSize: 0.38,
      luminanceSize: 0.86,
      randomSize: 0.26,
      dustSize: 0.22,
      glintSize: 1.86,
      maxSize: 2.72,
      baseAlpha: 0.034,
      luminanceAlpha: 0.16,
      sourceAlpha: 0.07,
      dustAlpha: 0.044,
      glintAlpha: 0.16,
      maxAlpha: 0.4,
      colorScale: 1.08,
      colorLift: 0.08,
      glintColor: 0.34,
      glintPower: 8,
      amplitudeBase: 0.24,
      amplitudeLuminance: 0.48,
      amplitudeDust: 0.2,
    }),
    createGaussianSplatVolumeLayer({
      name: "skyDepthPointCloud",
      count: midCount,
      seedOffset: 307,
      radiusMin: 0.1,
      radiusMax: 0.82,
      radiusExponent: 1.05,
      verticalScale: 0.92,
      zBias: 4,
      swirlStrength: 1.78,
      bandFrequency: 3.1,
      baseSize: 0.24,
      luminanceSize: 0.72,
      randomSize: 0.2,
      dustSize: 0.16,
      glintSize: 0.92,
      maxSize: 1.86,
      baseAlpha: 0.038,
      luminanceAlpha: 0.14,
      sourceAlpha: 0.064,
      dustAlpha: 0.044,
      glintAlpha: 0.11,
      maxAlpha: 0.36,
      colorScale: 0.94,
      colorLift: 0.046,
      glintColor: 0.22,
      glintPower: 10,
      amplitudeBase: 0.16,
      amplitudeLuminance: 0.42,
      amplitudeDust: 0.16,
    }),
    createGaussianSplatVolumeLayer({
      name: "ambientDeepSpacePointCloud",
      count: farCount,
      seedOffset: 601,
      radiusMin: 0.4,
      radiusMax: 1.05,
      radiusExponent: 0.82,
      verticalScale: 1.06,
      zBias: 12,
      swirlStrength: 1.32,
      bandFrequency: 2.4,
      baseSize: 0.12,
      luminanceSize: 0.44,
      randomSize: 0.14,
      dustSize: 0.08,
      glintSize: 0.5,
      maxSize: 0.92,
      baseAlpha: 0.024,
      luminanceAlpha: 0.08,
      sourceAlpha: 0.035,
      dustAlpha: 0.028,
      glintAlpha: 0.055,
      maxAlpha: 0.18,
      colorScale: 0.74,
      colorLift: 0.026,
      glintColor: 0.12,
      glintPower: 13,
      amplitudeBase: 0.08,
      amplitudeLuminance: 0.28,
      amplitudeDust: 0.1,
    }),
  ];

  function createGaussianSplatVolumeLayer(profile: {
    name: PointCloudLayerName;
    count: number;
    seedOffset: number;
    radiusMin: number;
    radiusMax: number;
    radiusExponent: number;
    verticalScale: number;
    zBias: number;
    swirlStrength: number;
    bandFrequency: number;
    baseSize: number;
    luminanceSize: number;
    randomSize: number;
    dustSize: number;
    glintSize: number;
    maxSize: number;
    baseAlpha: number;
    luminanceAlpha: number;
    sourceAlpha: number;
    dustAlpha: number;
    glintAlpha: number;
    maxAlpha: number;
    colorScale: number;
    colorLift: number;
    glintColor: number;
    glintPower: number;
    amplitudeBase: number;
    amplitudeLuminance: number;
    amplitudeDust: number;
  }): GeneratedPointCloudLayer {
    const positions = new Float32Array(profile.count * 3);
    const colors = new Float32Array(profile.count * 3);
    const sizes = new Float32Array(profile.count);
    const alphas = new Float32Array(profile.count);
    const randoms = new Float32Array(profile.count);
    const amplitudes = new Float32Array(profile.count);

    for (let index = 0; index < profile.count; index += 1) {
      const seed = index + profile.seedOffset;
      const sourceIndex = Math.floor(
        hash01(seed * 31 + profile.seedOffset) * header.vertexCount,
      );
      const sourceOffset = header.dataOffset + sourceIndex * header.stride;
      const rawColor = gaussianSplatColor(
        readProperty(view, sourceOffset, f0Property, 0),
        readProperty(view, sourceOffset, f1Property, 0),
        readProperty(view, sourceOffset, f2Property, 0),
      );
      const sampledAlpha = sigmoid(
        readProperty(view, sourceOffset, opacityProperty, 0),
      );
      const color = visualGaussianSplatColor(rawColor);
      const luminance =
        rawColor[0] * 0.2126 + rawColor[1] * 0.7152 + rawColor[2] * 0.0722;
      const theta = hash01(seed * 17 + 1) * Math.PI * 2;
      const verticalBase = hash01(seed * 17 + 2) * 2 - 1;
      const vertical = clamp(
        verticalBase * profile.verticalScale +
          Math.sin(theta * 1.7 + seed * 0.013) * 0.06,
        -1,
        1,
      );
      const horizontal = Math.sqrt(Math.max(0, 1 - vertical * vertical));
      const radius =
        profile.radiusMin +
        Math.pow(hash01(seed * 17 + 3), profile.radiusExponent) *
          (profile.radiusMax - profile.radiusMin);
      const swirl =
        theta +
        radius * profile.swirlStrength +
        Math.sin(theta * 2.6 + vertical * 3.2) * 0.1 +
        (hash01(seed * 17 + 4) - 0.5) * 0.2;
      const dustBand =
        Math.sin(
          swirl * profile.bandFrequency + vertical * 2.4 + radius * 7.2,
        ) *
          0.5 +
        0.5;
      const filament = Math.pow(dustBand, 2.15);
      const coreBias = 1 - Math.min(1, radius / Math.max(profile.radiusMax, 0.001));
      const positionOffset = index * 3;
      const random = hash01(sourceIndex + seed * 13);
      const glint = Math.pow(hash01(seed * 17 + 5), profile.glintPower);

      positions[positionOffset] =
        Math.cos(swirl) * horizontal * radius * radiusX +
        Math.sin(vertical * 8.1 + theta) * 3.4;
      positions[positionOffset + 1] =
        worldCenterY +
        vertical * radius * radiusY +
        Math.sin(swirl * 1.7) * 3.8;
      positions[positionOffset + 2] =
        worldCenterZ +
        profile.zBias +
        Math.sin(swirl) * horizontal * radius * radiusZ +
        Math.cos(theta * 1.9 + vertical) * 4.6;
      colors[positionOffset] = clamp01(
        Math.pow(color[0], 0.82) * profile.colorScale +
          profile.colorLift +
          glint * profile.glintColor,
      );
      colors[positionOffset + 1] = clamp01(
        Math.pow(color[1], 0.84) * profile.colorScale +
          profile.colorLift * 0.88 +
          glint * profile.glintColor * 0.92,
      );
      colors[positionOffset + 2] = clamp01(
        Math.pow(color[2], 0.82) * (profile.colorScale + 0.08) +
          profile.colorLift * 1.12 +
          glint * profile.glintColor * 1.12,
      );
      sizes[index] = Math.min(
        profile.maxSize,
        profile.baseSize +
          Math.pow(luminance, 0.76) * profile.luminanceSize +
          random * profile.randomSize +
          filament * profile.dustSize +
          coreBias * profile.dustSize * 0.5 +
          glint * profile.glintSize,
      );
      alphas[index] = Math.min(
        profile.maxAlpha,
        profile.baseAlpha +
          Math.pow(luminance, 0.66) * profile.luminanceAlpha +
          sampledAlpha * profile.sourceAlpha +
          filament * profile.dustAlpha +
          glint * profile.glintAlpha,
      );
      randoms[index] = random;
      amplitudes[index] = Math.min(
        1,
        Math.max(
          0.04,
          profile.amplitudeBase +
            luminance * profile.amplitudeLuminance +
            sampledAlpha * 0.12 +
            filament * profile.amplitudeDust +
            random * 0.08,
        ),
      );
    }

    return {
      name: profile.name,
      layerId: layerId[profile.name],
      count: profile.count,
      positions,
      colors,
      sizes,
      alphas,
      randoms,
      amplitudes,
    };
  }
}

function loadGaussianSplatDetailLayerFromBuffer(
  view: DataView,
  header: PlyHeader,
  properties: Map<string, PlyProperty>,
  options: LoadPlyOptions,
): GeneratedPointCloudLayer {
  const xProperty = properties.get("x");
  const yProperty = properties.get("y");
  const zProperty = properties.get("z");
  const f0Property = properties.get("f_dc_0");
  const f1Property = properties.get("f_dc_1");
  const f2Property = properties.get("f_dc_2");
  const opacityProperty = properties.get("opacity");
  const scale0Property = properties.get("scale_0");
  const scale1Property = properties.get("scale_1");
  const scale2Property = properties.get("scale_2");

  if (
    !xProperty ||
    !yProperty ||
    !zProperty ||
    !f0Property ||
    !f1Property ||
    !f2Property ||
    !opacityProperty ||
    !scale0Property ||
    !scale1Property ||
    !scale2Property
  ) {
    throw new Error("Gaussian Splat 鐐逛簯缂哄皯缁嗚妭灞傚瓧娈?");
  }

  const bounds = createEmptyBounds();
  for (let index = 0; index < header.vertexCount; index += 1) {
    const offset = header.dataOffset + index * header.stride;
    expandBounds(
      bounds,
      readProperty(view, offset, xProperty, 0),
      readProperty(view, offset, yProperty, 0),
      readProperty(view, offset, zProperty, 0),
    );
  }

  const count = sampleDetailPointCountFor(
    header.vertexCount,
    options.tier,
    options.reducedMotion,
  );
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
  const sceneScale = 620 / Math.max(spanX, spanZ, spanY * 2.2);

  for (let index = 0; index < count; index += 1) {
    const initialSourceIndex =
      count === header.vertexCount
        ? index
        : Math.floor((index / count) * header.vertexCount);
    let sourceIndex = initialSourceIndex;
    let x = 0;
    let y = 0;
    let z = 0;
    let alpha = 0;
    let luminance = 0;
    let rawColor: [number, number, number] = [0.5, 0.5, 0.5];

    for (let attempt = 0; attempt < 8; attempt += 1) {
      const candidateIndex =
        (initialSourceIndex + attempt * 9973 + Math.floor(hash01(index + attempt) * 4096)) %
        header.vertexCount;
      const sourceOffset = header.dataOffset + candidateIndex * header.stride;
      const baseScale0 = Math.exp(readProperty(view, sourceOffset, scale0Property, -4.5));
      const baseScale1 = Math.exp(readProperty(view, sourceOffset, scale1Property, -4.5));
      const baseScale2 = Math.exp(readProperty(view, sourceOffset, scale2Property, -4.5));
      const maxSplatScale =
        Math.max(baseScale0, baseScale1, baseScale2) * sceneScale;
      const candidateColor = gaussianSplatColor(
        readProperty(view, sourceOffset, f0Property, 0),
        readProperty(view, sourceOffset, f1Property, 0),
        readProperty(view, sourceOffset, f2Property, 0),
      );
      const candidateLuminance =
        candidateColor[0] * 0.2126 +
        candidateColor[1] * 0.7152 +
        candidateColor[2] * 0.0722;
      const candidateAlpha = sigmoid(readProperty(view, sourceOffset, opacityProperty, 0));
      const shouldUseCandidate =
        maxSplatScale <= 1.28 ||
        candidateLuminance >= 0.2 ||
        candidateAlpha >= 0.28 ||
        attempt === 7;

      if (!shouldUseCandidate) {
        continue;
      }

      sourceIndex = candidateIndex;
      x = readProperty(view, sourceOffset, xProperty, 0);
      y = readProperty(view, sourceOffset, yProperty, 0);
      z = readProperty(view, sourceOffset, zProperty, 0);
      alpha = candidateAlpha;
      luminance = candidateLuminance;
      rawColor = candidateColor;
      break;
    }

    const depth = (z - bounds.minZ) / spanZ;
    const random = hash01(sourceIndex);
    const positionOffset = index * 3;
    const color = visualGaussianSplatColor(rawColor);

    positions[positionOffset] = (x - centerX) * sceneScale;
    positions[positionOffset + 1] = (y - centerY) * sceneScale - 42;
    positions[positionOffset + 2] = depth * spanZ * sceneScale + 44;
    colors[positionOffset] = clamp01(Math.pow(color[0], 0.82) * 1.08 + 0.035);
    colors[positionOffset + 1] = clamp01(Math.pow(color[1], 0.82) * 1.06 + 0.028);
    colors[positionOffset + 2] = clamp01(Math.pow(color[2], 0.82) * 1.16 + 0.042);
    sizes[index] = Math.min(
      2.15,
      0.42 + Math.pow(luminance, 0.7) * 1.05 + alpha * 0.24 + random * 0.22,
    );
    alphas[index] = Math.min(
      0.68,
      0.1 + Math.pow(luminance, 0.64) * 0.44 + alpha * 0.16 + random * 0.035,
    );
    randoms[index] = random;
    amplitudes[index] = Math.min(
      1,
      Math.max(0.05, 0.14 + luminance * 0.58 + alpha * 0.16 + depth * 0.12 + random * 0.08),
    );
  }

  return {
    name: "midGroundMistPointCloud",
    layerId: layerId.midGroundMistPointCloud,
    count,
    positions,
    colors,
    sizes,
    alphas,
    randoms,
    amplitudes,
  };
}
