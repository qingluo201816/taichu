export const pointCloudVertexShader = `
attribute float aSize;
attribute float aAlpha;
attribute float aRandom;

uniform float uTime;
uniform float uPixelRatio;
uniform float uEntryProgress;
uniform float uDenseProgress;
uniform float uFocusProgress;
uniform float uGlobalOpacity;
uniform float uMaxPointSize;
uniform float uNearFadeDistance;
uniform float uLayerDrift;
uniform float uFocusDim;

varying vec3 vColor;
varying float vAlpha;

void main() {
  vec3 transformed = position;

  float phase = aRandom * 6.28318530718;
  float breath = sin(uTime * 0.42 + phase) * 0.045 * uLayerDrift;
  transformed.y += breath;
  transformed.x += cos(uTime * 0.18 + phase) * 0.025 * uLayerDrift;

  float entryPull = uEntryProgress * (aRandom - 0.5) * 2.2;
  transformed.z -= entryPull;
  transformed.y += uEntryProgress * sin(phase * 1.7) * 0.62;

  float denseStretch = uDenseProgress * (aRandom - 0.5) * 7.5;
  transformed.z += denseStretch;
  transformed.x += sin(phase * 2.0) * uDenseProgress * 0.9;

  vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
  float depth = max(1.0, -mvPosition.z);
  float perspectiveSize = aSize * uPixelRatio * (360.0 / depth);
  gl_PointSize = clamp(perspectiveSize, 0.35, uMaxPointSize);
  gl_Position = projectionMatrix * mvPosition;

  float nearFade = smoothstep(2.5, uNearFadeDistance, depth);
  float focusFade = mix(1.0, uFocusDim, uFocusProgress);
  vColor = color;
  vAlpha = aAlpha * uGlobalOpacity * nearFade * focusFade;
}
`;

export const pointCloudFragmentShader = `
precision mediump float;

varying vec3 vColor;
varying float vAlpha;

void main() {
  vec2 coord = gl_PointCoord - vec2(0.5);
  float distanceFromCenter = length(coord);
  float crispCircle = smoothstep(0.48, 0.28, distanceFromCenter);
  float pinCore = smoothstep(0.18, 0.0, distanceFromCenter);
  vec3 color = vColor * (0.9 + pinCore * 0.2);
  float alpha = vAlpha * crispCircle;

  if (alpha <= 0.012) {
    discard;
  }

  gl_FragColor = vec4(color, alpha);
}
`;
