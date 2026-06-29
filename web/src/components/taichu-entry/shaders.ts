export const pointCloudVertexShader = `
attribute float aSize;
attribute float aAlpha;
attribute float aRandom;
attribute float aAmplitude;

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
uniform float uAudioLow;
uniform float uAudioMid;
uniform float uAudioHigh;
uniform float uPulseStrength;

varying vec3 vColor;
varying float vAlpha;
varying float vCore;
varying float vMist;

void main() {
  vec3 transformed = position;

  float phase = aRandom * 6.28318530718;
  float slowPulse = sin(uTime * 0.34 + phase);
  float lateralPulse = cos(uTime * 0.19 + phase * 1.7);
  float audioEnergy = clamp(uAudioLow * 0.48 + uAudioMid * 0.34 + uAudioHigh * 0.18, 0.0, 1.0);
  float pointPulse = aAmplitude * uPulseStrength * (0.42 + audioEnergy * 0.72);
  transformed.y += slowPulse * 0.032 * uLayerDrift;
  transformed.x += lateralPulse * 0.022 * uLayerDrift;
  transformed.y += slowPulse * pointPulse * 0.18;
  transformed.x += lateralPulse * pointPulse * 0.12;
  transformed.z += sin(uTime * 0.27 + phase * 0.7) * aAmplitude * uAudioLow * 0.34;

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
  float amplitudeSize = 1.0 + pointPulse * (0.18 + uAudioHigh * 0.22);
  gl_PointSize = clamp(perspectiveSize * denseBoost * amplitudeSize, 0.48, uMaxPointSize);
  gl_Position = projectionMatrix * mvPosition;

  float nearFade = smoothstep(3.0, uNearFadeDistance, depth);
  float farMist = smoothstep(360.0, 920.0, depth);
  float focusFade = mix(1.0, uFocusDim, uFocusProgress);
  vColor = color;
  vAlpha =
    aAlpha *
    uGlobalOpacity *
    nearFade *
    focusFade *
    mix(1.0, 0.74, farMist) *
    (1.0 + pointPulse * 0.16);
  vCore = clamp(aSize / max(uMaxPointSize, 0.001), 0.0, 1.0);
  vMist = farMist;
}
`;

export const pointCloudFragmentShader = `
precision highp float;

varying vec3 vColor;
varying float vAlpha;
varying float vCore;
varying float vMist;

void main() {
  vec2 coord = gl_PointCoord - vec2(0.5);
  float distanceFromCenter = length(coord);
  float halo = smoothstep(0.5, 0.22, distanceFromCenter);
  float disc = smoothstep(0.48, 0.34, distanceFromCenter);
  float core = smoothstep(0.23, 0.02, distanceFromCenter);
  vec3 color = min(vColor * (1.06 + halo * 0.08 + core * 0.16 + vCore * 0.05), vec3(1.0));
  color = mix(color, vec3(0.14, 0.16, 0.22), vMist * 0.16);
  float alpha = min(vAlpha * (disc * 0.82 + halo * 0.2 + core * 0.12) * (1.0 - vMist * 0.1), 1.0);

  if (alpha <= 0.007) {
    discard;
  }

  gl_FragColor = vec4(color, alpha);
}
`;
