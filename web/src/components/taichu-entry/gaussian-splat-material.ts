import * as THREE from "three";

import type {
  GeneratedGaussianSplatLayer,
  PointCloudMaterialConfig,
} from "./types";

const gaussianSplatVertexShader = `
attribute vec3 iCenter;
attribute vec3 iColor;
attribute float iAlpha;
attribute vec3 iScale;
attribute vec4 iRotation;
attribute float iRandom;
attribute float iAmplitude;

uniform float uTime;
uniform float uEntryProgress;
uniform float uDenseProgress;
uniform float uFocusProgress;
uniform float uGlobalOpacity;
uniform float uLayerDrift;
uniform float uFocusDim;
uniform float uAudioLow;
uniform float uAudioMid;
uniform float uAudioHigh;
uniform float uPulseStrength;

varying vec2 vGaussianCoord;
varying vec3 vColor;
varying float vAlpha;
varying float vMist;

vec3 rotateByQuaternion(vec3 value, vec4 quaternion) {
  vec3 vector = quaternion.yzw;
  float scalar = quaternion.x;
  return value + 2.0 * cross(vector, cross(vector, value) + scalar * value);
}

vec3 limitAxisLength(vec3 axis, float maxLength) {
  float axisLength = length(axis);
  if (axisLength <= 0.00001) {
    return axis;
  }
  return axis * min(1.0, maxLength / axisLength);
}

vec3 safeNormalize(vec3 axis) {
  float axisLength = length(axis);
  if (axisLength <= 0.00001) {
    return vec3(0.0, 0.0, 1.0);
  }
  return axis / axisLength;
}

void main() {
  vec3 center = iCenter;
  float phase = iRandom * 6.28318530718;
  float slowPulse = sin(uTime * 0.34 + phase);
  float lateralPulse = cos(uTime * 0.19 + phase * 1.7);
  float audioEnergy = clamp(uAudioLow * 0.48 + uAudioMid * 0.34 + uAudioHigh * 0.18, 0.0, 1.0);
  float pointPulse = iAmplitude * uPulseStrength * (0.42 + audioEnergy * 0.72);

  center.y += slowPulse * 0.034 * uLayerDrift;
  center.x += lateralPulse * 0.024 * uLayerDrift;
  center.y += slowPulse * pointPulse * 0.22;
  center.x += lateralPulse * pointPulse * 0.14;
  center.z += sin(uTime * 0.27 + phase * 0.7) * iAmplitude * uAudioLow * 0.38;

  center.z -= uEntryProgress * (iRandom - 0.5) * 8.6;
  center.y += uEntryProgress * sin(phase * 1.7) * 0.46;
  center.x += uEntryProgress * cos(phase * 1.3) * 0.58;

  center.z += uDenseProgress * (iRandom - 0.5) * 17.0;
  center.x += sin(phase * 2.0) * uDenseProgress * 1.35;
  center.y += cos(phase * 2.3) * uDenseProgress * 0.76;

  vec4 mvCenter = modelViewMatrix * vec4(center, 1.0);
  float depth = max(1.0, -mvCenter.z);
  float maxAxisLength = mix(0.5, 1.42, smoothstep(24.0, 190.0, depth));
  vec2 gaussianCoord = position.xy * 1.72;
  vec3 axisX = rotateByQuaternion(vec3(iScale.x, 0.0, 0.0), iRotation);
  vec3 axisY = rotateByQuaternion(vec3(0.0, iScale.y, 0.0), iRotation);
  vec3 axisZ = rotateByQuaternion(vec3(0.0, 0.0, iScale.z), iRotation);
  axisX = limitAxisLength(axisX, maxAxisLength);
  axisY = limitAxisLength(axisY, maxAxisLength);
  axisZ = limitAxisLength(axisZ, maxAxisLength * 0.88);
  vec3 cameraRight = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
  vec3 cameraUp = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
  float rightWeight = max(abs(dot(safeNormalize(axisX), cameraRight)), abs(dot(safeNormalize(axisZ), cameraRight)));
  float upWeight = max(abs(dot(safeNormalize(axisY), cameraUp)), abs(dot(safeNormalize(axisZ), cameraUp)));
  vec3 basisX = mix(axisZ, axisX, rightWeight);
  vec3 basisY = mix(axisZ, axisY, upWeight);
  vec3 transformed = center + basisX * gaussianCoord.x + basisY * gaussianCoord.y;
  vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
  float nearFade = smoothstep(3.2, 8.4, depth);
  float farMist = smoothstep(360.0, 920.0, depth);
  float focusFade = mix(1.0, uFocusDim, uFocusProgress);

  vGaussianCoord = gaussianCoord;
  vColor = iColor;
  vAlpha = iAlpha * uGlobalOpacity * nearFade * focusFade * mix(1.0, 0.76, farMist) * (1.0 + pointPulse * 0.18);
  vMist = farMist;
  gl_Position = projectionMatrix * mvPosition;
}
`;

const gaussianSplatFragmentShader = `
precision highp float;

varying vec2 vGaussianCoord;
varying vec3 vColor;
varying float vAlpha;
varying float vMist;

void main() {
  float radius = dot(vGaussianCoord, vGaussianCoord);
  float gaussian = exp(-radius * 1.2);
  float core = exp(-radius * 4.1);
  vec3 color = min(vColor * (1.1 + core * 0.32), vec3(1.0));
  color = mix(color, vec3(0.12, 0.14, 0.2), vMist * 0.12);
  float alpha = min(vAlpha * gaussian * (1.0 - vMist * 0.08), 1.0);

  if (alpha <= 0.006) {
    discard;
  }

  gl_FragColor = vec4(color, alpha);
}
`;

export function createGaussianSplatMesh({
  layer,
  materialConfig,
}: {
  layer: GeneratedGaussianSplatLayer;
  materialConfig: PointCloudMaterialConfig;
}): {
  geometry: THREE.InstancedBufferGeometry;
  material: THREE.ShaderMaterial;
  mesh: THREE.Mesh;
} {
  const geometry = new THREE.InstancedBufferGeometry();
  geometry.instanceCount = layer.count;
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(
      new Float32Array([
        -1, -1, 0,
        1, -1, 0,
        1, 1, 0,
        -1, 1, 0,
      ]),
      3,
    ),
  );
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.setAttribute("iCenter", new THREE.InstancedBufferAttribute(layer.centers, 3));
  geometry.setAttribute("iColor", new THREE.InstancedBufferAttribute(layer.colors, 3));
  geometry.setAttribute("iAlpha", new THREE.InstancedBufferAttribute(layer.alphas, 1));
  geometry.setAttribute("iScale", new THREE.InstancedBufferAttribute(layer.scales, 3));
  geometry.setAttribute("iRotation", new THREE.InstancedBufferAttribute(layer.rotations, 4));
  geometry.setAttribute("iRandom", new THREE.InstancedBufferAttribute(layer.randoms, 1));
  geometry.setAttribute("iAmplitude", new THREE.InstancedBufferAttribute(layer.amplitudes, 1));

  const material = new THREE.ShaderMaterial({
    vertexShader: gaussianSplatVertexShader,
    fragmentShader: gaussianSplatFragmentShader,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: THREE.NormalBlending,
    uniforms: {
      uTime: { value: 0 },
      uEntryProgress: { value: 0 },
      uDenseProgress: { value: 0 },
      uFocusProgress: { value: 0 },
      uGlobalOpacity: { value: 0.86 },
      uLayerDrift: { value: 0.18 },
      uFocusDim: { value: 0.18 },
      uAudioLow: { value: materialConfig.audioLow },
      uAudioMid: { value: materialConfig.audioMid },
      uAudioHigh: { value: materialConfig.audioHigh },
      uPulseStrength: { value: materialConfig.pulseStrength },
    },
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;

  return { geometry, material, mesh };
}
