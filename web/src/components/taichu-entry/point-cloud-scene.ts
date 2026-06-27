import { gsap } from "gsap";
import * as THREE from "three";

import { layerCountsForTier, detectPerformanceTier } from "./performance";
import { generatePointCloudLayers } from "./point-cloud-generators";
import {
  pointCloudFragmentShader,
  pointCloudVertexShader,
} from "./shaders";
import type {
  EntryState,
  GeneratedPointCloudLayer,
  PointCloudLayerName,
  PointCloudSceneOptions,
} from "./types";

type RuntimeLayer = {
  name: PointCloudLayerName;
  geometry: THREE.BufferGeometry;
  material: THREE.ShaderMaterial;
  points: THREE.Points;
  baseOpacity: number;
};

const baseLayerOpacity: Record<PointCloudLayerName, number> = {
  foregroundGroundPointCloud: 1.28,
  midGroundMistPointCloud: 1.16,
  horizonGlowBandPointCloud: 1.18,
  sideBoundaryPointCloud: 1.18,
  skyDepthPointCloud: 0.94,
  ambientDeepSpacePointCloud: 0.74,
  distantEnvironmentPointCloud: 1.02,
  distantPalacePointCloud: 1,
  transitionDensePointCloud: 0,
  focusParticle: 0,
};

const layerDrift: Record<PointCloudLayerName, number> = {
  foregroundGroundPointCloud: 0.3,
  midGroundMistPointCloud: 0.82,
  horizonGlowBandPointCloud: 0.52,
  sideBoundaryPointCloud: 0.42,
  skyDepthPointCloud: 0.24,
  ambientDeepSpacePointCloud: 0.2,
  distantEnvironmentPointCloud: 0.28,
  distantPalacePointCloud: 0.1,
  transitionDensePointCloud: 1.08,
  focusParticle: 0.1,
};

export class TaichuPointCloudScene {
  private readonly container: HTMLElement;
  private readonly reducedMotion: boolean;
  private readonly onEnter: () => void;
  private readonly onStateChange?: (state: EntryState) => void;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly layers: RuntimeLayer[] = [];
  private readonly cameraTarget = { x: 0, y: -0.35, z: 184 };
  private readonly sceneStart = performance.now();
  private animationFrameId = 0;
  private disposed = false;
  private state: EntryState = "idle";
  private timeline: gsap.core.Timeline | null = null;
  private pointerX = 0;
  private pointerY = 0;
  private frameCount = 0;
  private fpsStart = 0;
  private degraded = false;

  constructor(options: PointCloudSceneOptions) {
    this.container = options.container;
    this.reducedMotion = options.reducedMotion;
    this.onEnter = options.onEnter;
    this.onStateChange = options.onStateChange;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x100b12, 0.0029);

    this.camera = new THREE.PerspectiveCamera(70, 1, 0.1, 430);
    this.camera.position.set(0, 2.05, 15);
    this.camera.lookAt(this.cameraTarget.x, this.cameraTarget.y, this.cameraTarget.z);

    this.renderer = new THREE.WebGLRenderer({
      alpha: false,
      antialias: false,
      powerPreference: "high-performance",
    });
    this.renderer.setClearColor(0x100b12, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.style.position = "absolute";
    this.renderer.domElement.style.inset = "0";
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.container.appendChild(this.renderer.domElement);

    this.buildPointCloud();
    this.resize();
    this.container.addEventListener("pointermove", this.onPointerMove);
    window.addEventListener("resize", this.resize);
    this.fpsStart = performance.now();
    this.animate();
  }

  enter(): void {
    if (this.state !== "idle") {
      return;
    }

    if (this.reducedMotion) {
      this.enterWithReducedMotion();
      return;
    }

    this.setState("entering");
    this.timeline?.kill();
    this.timeline = gsap.timeline({
      defaults: { ease: "power2.inOut" },
      onComplete: () => {
        this.setState("completed");
        this.onEnter();
      },
    });

    this.timeline.to(this.camera.position, { z: 76, y: 2.72, duration: 1.45 }, 0);
    this.timeline.to(this.cameraTarget, { y: 1.1, z: 184, duration: 1.45 }, 0);
    this.timeline.to(
      this.camera,
      {
        fov: 50,
        duration: 1.45,
        onUpdate: () => this.camera.updateProjectionMatrix(),
      },
      0,
    );
    this.tweenUniform("uEntryProgress", 1, 1.45, 0);
    this.tweenLayerOpacity(["distantPalacePointCloud"], 0.16, 1.1, 0.35);
    this.tweenLayerOpacity(["transitionDensePointCloud"], 0.32, 0.75, 0.72);

    this.timeline.add(() => this.setState("dense-transition"), 1.34);
    this.timeline.to(this.camera.position, { z: 116, y: 3.42, duration: 1 }, 1.45);
    this.timeline.to(this.cameraTarget, { x: 0.1, y: 5.05, z: 132, duration: 1 }, 1.45);
    this.tweenUniform("uDenseProgress", 1, 1, 1.45);
    this.tweenLayerOpacity(["transitionDensePointCloud"], 1, 0.55, 1.45);
    this.tweenLayerOpacity(
      [
        "foregroundGroundPointCloud",
        "sideBoundaryPointCloud",
        "skyDepthPointCloud",
        "ambientDeepSpacePointCloud",
        "distantEnvironmentPointCloud",
      ],
      0.3,
      0.75,
      1.58,
    );

    this.timeline.add(() => this.setState("focus"), 2.48);
    this.timeline.to(this.camera.position, { x: 0.42, y: 4.15, z: 124, duration: 0.9 }, 2.48);
    this.timeline.to(this.cameraTarget, { x: 0.74, y: 4.45, z: 132, duration: 0.9 }, 2.48);
    this.tweenLayerOpacity(["transitionDensePointCloud"], 0.12, 0.8, 2.48);
    this.tweenLayerOpacity(["focusParticle"], 1, 0.5, 2.55);
    this.tweenUniform("uFocusProgress", 1, 0.9, 2.48);
    this.tweenUniform("uGlobalOpacity", 0.14, 0.75, 3.05, [
      "focusParticle",
      "transitionDensePointCloud",
    ]);
    this.tweenLayerOpacity(["focusParticle"], 1, 0.5, 3.05);
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.timeline?.kill();
    window.cancelAnimationFrame(this.animationFrameId);
    this.container.removeEventListener("pointermove", this.onPointerMove);
    window.removeEventListener("resize", this.resize);

    for (const layer of this.layers) {
      this.scene.remove(layer.points);
      layer.geometry.dispose();
      layer.material.dispose();
    }

    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private enterWithReducedMotion(): void {
    this.setState("entering");
    this.timeline?.kill();
    this.timeline = gsap.timeline({
      defaults: { ease: "power2.out" },
      onComplete: () => {
        this.setState("completed");
        this.onEnter();
      },
    });
    this.tweenLayerOpacity(["focusParticle"], 0.9, 0.2, 0);
    this.tweenUniform("uGlobalOpacity", 0.1, 0.36, 0, ["focusParticle"]);
  }

  private buildPointCloud(): void {
    const tier = detectPerformanceTier();
    const counts = layerCountsForTier(tier, this.reducedMotion);
    const generatedLayers = generatePointCloudLayers(counts);

    for (const layer of generatedLayers) {
      this.addLayer(layer);
    }
  }

  private addLayer(layer: GeneratedPointCloudLayer): void {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(layer.positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(layer.colors, 3));
    geometry.setAttribute("aSize", new THREE.BufferAttribute(layer.sizes, 1));
    geometry.setAttribute("aAlpha", new THREE.BufferAttribute(layer.alphas, 1));
    geometry.setAttribute("aRandom", new THREE.BufferAttribute(layer.randoms, 1));

    const material = new THREE.ShaderMaterial({
      vertexShader: pointCloudVertexShader,
      fragmentShader: pointCloudFragmentShader,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.NormalBlending,
      vertexColors: true,
      uniforms: {
        uTime: { value: 0 },
        uPixelRatio: { value: this.pixelRatio() },
        uEntryProgress: { value: 0 },
        uDenseProgress: { value: 0 },
        uFocusProgress: { value: 0 },
        uGlobalOpacity: { value: baseLayerOpacity[layer.name] },
        uMaxPointSize: { value: layer.name === "focusParticle" ? 7.4 : 5.9 },
        uNearFadeDistance: { value: 7.2 },
        uLayerDrift: { value: layerDrift[layer.name] },
        uFocusDim: { value: layer.name === "focusParticle" ? 1 : 0.16 },
      },
    });

    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    this.scene.add(points);
    this.layers.push({
      name: layer.name,
      geometry,
      material,
      points,
      baseOpacity: baseLayerOpacity[layer.name],
    });
  }

  private tweenUniform(
    uniformName: string,
    value: number,
    duration: number,
    position: number,
    exclude: PointCloudLayerName[] = [],
  ): void {
    if (!this.timeline) {
      return;
    }
    const excluded = new Set(exclude);
    for (const layer of this.layers) {
      if (excluded.has(layer.name)) {
        continue;
      }
      this.timeline.to(
        layer.material.uniforms[uniformName],
        { value, duration },
        position,
      );
    }
  }

  private tweenLayerOpacity(
    names: PointCloudLayerName[],
    opacity: number,
    duration: number,
    position: number,
  ): void {
    if (!this.timeline) {
      return;
    }
    const selected = new Set(names);
    for (const layer of this.layers) {
      if (!selected.has(layer.name)) {
        continue;
      }
      this.timeline.to(
        layer.material.uniforms.uGlobalOpacity,
        { value: opacity, duration },
        position,
      );
    }
  }

  private setState(state: EntryState): void {
    this.state = state;
    this.onStateChange?.(state);
  }

  private readonly onPointerMove = (event: PointerEvent): void => {
    const rect = this.container.getBoundingClientRect();
    this.pointerX = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    this.pointerY = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
  };

  private readonly resize = (): void => {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(this.pixelRatio());
    this.renderer.setSize(width, height, false);

    for (const layer of this.layers) {
      layer.material.uniforms.uPixelRatio.value = this.pixelRatio();
    }
  };

  private animate = (): void => {
    if (this.disposed) {
      return;
    }

    const elapsed = (performance.now() - this.sceneStart) / 1000;
    for (const layer of this.layers) {
      layer.material.uniforms.uTime.value = elapsed;
    }

    if (this.state === "idle") {
      const targetX = this.pointerX * 2.35;
      const targetY = 2.05 - this.pointerY * 0.34;
      this.camera.position.x += (targetX - this.camera.position.x) * 0.035;
      this.camera.position.y += (targetY - this.camera.position.y) * 0.035;
      this.cameraTarget.x += (this.pointerX * 3.8 - this.cameraTarget.x) * 0.025;
      this.cameraTarget.y += (-0.35 - this.pointerY * 0.68 - this.cameraTarget.y) * 0.025;
    }

    this.camera.lookAt(
      this.cameraTarget.x,
      this.cameraTarget.y,
      this.cameraTarget.z,
    );
    this.renderer.render(this.scene, this.camera);
    this.checkFrameBudget();
    this.animationFrameId = window.requestAnimationFrame(this.animate);
  };

  private checkFrameBudget(): void {
    if (this.degraded || this.state !== "idle") {
      return;
    }

    this.frameCount += 1;
    const now = performance.now();
    const elapsed = now - this.fpsStart;
    if (elapsed < 2200) {
      return;
    }

    const averageFps = this.frameCount / (elapsed / 1000);
    if (averageFps < 45) {
      this.degraded = true;
      const heavyLayers: PointCloudLayerName[] = [
        "sideBoundaryPointCloud",
        "skyDepthPointCloud",
        "ambientDeepSpacePointCloud",
      ];
      for (const layer of this.layers) {
        if (heavyLayers.includes(layer.name)) {
          layer.material.uniforms.uGlobalOpacity.value = layer.baseOpacity * 0.55;
        }
      }
    }
  }

  private pixelRatio(): number {
    return Math.min(window.devicePixelRatio || 1, 1.75);
  }
}
