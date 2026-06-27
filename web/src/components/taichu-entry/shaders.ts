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
varying float vCore;

void main() {
  vec3 transformed = position;

  float phase = aRandom * 6.28318530718;
  float slowPulse = sin(uTime * 0.34 + phase);
  float lateralPulse = cos(uTime * 0.19 + phase * 1.7);
  transformed.y += slowPulse * 0.032 * uLayerDrift;
  transformed.x += lateralPulse * 0.022 * uLayerDrift;

  float entryPull = uEntryProgress * (aRandom - 0.5) * 8.6;
  transformed.z -= entryPull;
  transformed.y += uEntryProgress * sin(phase * 1.7) * 0.46;
  transformed.x += uEntryProgress * cos(phase * 1.3) * 0.58;

  float denseStretch = uDenseProgress * (aRandom - 0.5) * 17.0;
  transformed.z += denseStretch;
  transformed.x += sin(phase * 2.0) * uDenseProgress * 1.35;
  transformed.y += cos(phase * 2.3) * uDenseProgress * 0.76;

  vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
  float depth = max(1.0, -mvPosition.z);
  float perspectiveSize = aSize * uPixelRatio * (410.0 / depth);
  float denseBoost = 1.0 + uDenseProgress * 0.18;
  gl_PointSize = clamp(perspectiveSize * denseBoost, 0.48, uMaxPointSize);
  gl_Position = projectionMatrix * mvPosition;

  float nearFade = smoothstep(3.0, uNearFadeDistance, depth);
  float focusFade = mix(1.0, uFocusDim, uFocusProgress);
  vColor = color;
  vAlpha = aAlpha * uGlobalOpacity * nearFade * focusFade;
  vCore = clamp(aSize / max(uMaxPointSize, 0.001), 0.0, 1.0);
}
`;

export const pointCloudFragmentShader = `
precision highp float;

varying vec3 vColor;
varying float vAlpha;
varying float vCore;

void main() {
  vec2 coord = gl_PointCoord - vec2(0.5);
  float distanceFromCenter = length(coord);
  float disc = smoothstep(0.5, 0.39, distanceFromCenter);
  float core = smoothstep(0.23, 0.02, distanceFromCenter);
  vec3 color = min(vColor * (1.12 + core * 0.12 + vCore * 0.04), vec3(1.0));
  float alpha = min(vAlpha * (disc * 1.05 + core * 0.1), 1.0);

  if (alpha <= 0.007) {
    discard;
  }

  gl_FragColor = vec4(color, alpha);
}
`;
