import { gsap } from "gsap";
import * as THREE from "three";

import {
  fallbackFocusParticle,
  generateFallbackPointCloudLayers,
} from "./generated-fallback-point-cloud";
import { createGaussianSplatMesh } from "./gaussian-splat-material";
import { layerCountsForTier, detectPerformanceTier } from "./performance";
import { loadPointCloudAsset } from "./point-cloud-asset";
import { PointCloudCameraController } from "./point-cloud-camera-controller";
import {
  createPointCloudMaterial,
  layerBaseOpacity,
} from "./point-cloud-material";
import { taichuEntrySceneConfig } from "./point-cloud-scene-config";
import { PointCloudInteractionLayer } from "./point-cloud-interaction-layer";
import type {
  EntryState,
  GeneratedGaussianSplatLayer,
  GeneratedPointCloudLayer,
  PointCloudLayerName,
  PointCloudSceneConfig,
  PointCloudSceneOptions,
} from "./types";

type RuntimeLayer = {
  name: PointCloudLayerName;
  geometry: THREE.BufferGeometry | THREE.InstancedBufferGeometry;
  material: THREE.ShaderMaterial;
  object: THREE.Object3D;
  baseOpacity: number;
};

export class TaichuPointCloudScene {
  private readonly container: HTMLElement;
  private readonly reducedMotion: boolean;
  private readonly config: PointCloudSceneConfig;
  private readonly onEnter: () => void;
  private readonly onStateChange?: (state: EntryState) => void;
  private readonly onAssetStatusChange?: PointCloudSceneOptions["onAssetStatusChange"];
  private readonly onCameraPositionChange?: PointCloudSceneOptions["onCameraPositionChange"];
  private readonly onRenderError?: PointCloudSceneOptions["onRenderError"];
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly cameraTarget = { x: 0, y: 0, z: 0 };
  private readonly cameraController: PointCloudCameraController;
  private readonly interactionLayer: PointCloudInteractionLayer;
  private readonly layers: RuntimeLayer[] = [];
  private readonly sceneStart = performance.now();
  private lastFrameTime = performance.now();
  private lastCameraPositionNotify = 0;
  private animationFrameId = 0;
  private enterTimeoutId: number | null = null;
  private disposed = false;
  private state: EntryState = "idle";
  private timeline: gsap.core.Timeline | null = null;
  private frameCount = 0;
  private fpsStart = 0;
  private degraded = false;

  constructor(options: PointCloudSceneOptions) {
    this.container = options.container;
    this.reducedMotion = options.reducedMotion;
    this.config = options.config ?? taichuEntrySceneConfig;
    this.onEnter = options.onEnter;
    this.onStateChange = options.onStateChange;
    this.onAssetStatusChange = options.onAssetStatusChange;
    this.onCameraPositionChange = options.onCameraPositionChange;
    this.onRenderError = options.onRenderError;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x030713, 0.00125);

    this.camera = new THREE.PerspectiveCamera(this.config.cameraNav.fov, 1, 0.1, 1120);
    this.cameraController = new PointCloudCameraController({
      camera: this.camera,
      cameraTarget: this.cameraTarget,
      reducedMotion: this.reducedMotion,
      cameraNav: this.config.cameraNav,
      exploration: this.config.exploration,
      desktopExplorationEnabled: this.isDesktopExplorationViewport(),
    });
    this.interactionLayer = new PointCloudInteractionLayer([
      ...this.config.hotspots,
    ]);

    this.renderer = new THREE.WebGLRenderer({
      alpha: false,
      antialias: false,
      powerPreference: "high-performance",
    });
    this.renderer.setClearColor(0x030713, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.style.position = "absolute";
    this.renderer.domElement.style.inset = "0";
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.renderer.domElement.style.cursor = "none";
    this.renderer.domElement.style.touchAction = "none";
    this.container.appendChild(this.renderer.domElement);

    this.resize();
    this.container.addEventListener("pointermove", this.onPointerMove);
    this.container.addEventListener("pointerdown", this.onPointerDown);
    this.container.addEventListener("pointercancel", this.onPointerCancel);
    this.container.addEventListener("wheel", this.onWheel, { passive: false });
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
    window.addEventListener("pointerup", this.onPointerUp);
    window.addEventListener("resize", this.resize);
    this.fpsStart = performance.now();
    this.notifyCameraPosition(true);
    this.animate();
    void this.buildPointCloud();
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
    this.clearEnterTimeout();
    this.timeline = gsap.timeline({
      defaults: { ease: "power2.inOut" },
      onComplete: () => this.completeEntry(),
    });
    this.enterTimeoutId = window.setTimeout(() => this.completeEntry(), 4200);

    this.cameraController.tweenTo(this.timeline, this.config.cameraEnter, 1.45, 0);
    this.tweenUniform("uEntryProgress", 1, 1.45, 0);
    this.tweenLayerOpacity(["horizonGlowBandPointCloud", "distantPalacePointCloud"], 0.6, 1.1, 0.35);
    this.tweenLayerOpacity(["transitionDensePointCloud"], 0.3, 0.75, 0.72);

    this.timeline.add(() => this.setState("dense-transition"), 1.34);
    this.cameraController.tweenTo(this.timeline, this.config.cameraChapter, 1, 1.45);
    this.tweenUniform("uDenseProgress", 1, 1, 1.45);
    this.tweenLayerOpacity(["transitionDensePointCloud"], 0.92, 0.55, 1.45);
    this.tweenLayerOpacity(
      [
        "sourcePointCloud",
        "foregroundGroundPointCloud",
        "midGroundMistPointCloud",
        "horizonGlowBandPointCloud",
        "sideBoundaryPointCloud",
        "skyDepthPointCloud",
        "ambientDeepSpacePointCloud",
        "distantEnvironmentPointCloud",
      ],
      0.42,
      0.75,
      1.58,
    );

    this.timeline.add(() => this.setState("focus"), 2.48);
    this.cameraController.tweenTo(this.timeline, this.config.cameraFocus, 0.9, 2.48);
    this.tweenLayerOpacity(
      [
        "sourcePointCloud",
        "foregroundGroundPointCloud",
        "midGroundMistPointCloud",
        "horizonGlowBandPointCloud",
        "ambientDeepSpacePointCloud",
        "transitionDensePointCloud",
      ],
      0.18,
      0.8,
      2.48,
    );
    this.tweenLayerOpacity(["focusParticle"], 1, 0.5, 2.55);
    this.tweenUniform("uFocusProgress", 1, 0.9, 2.48);
    this.tweenUniform("uGlobalOpacity", 0.14, 0.75, 3.05, [
      "focusParticle",
      "transitionDensePointCloud",
    ]);
    this.tweenLayerOpacity(["focusParticle"], 1, 0.5, 3.05);
  }

  setAudioBands(low: number, mid: number, high: number): void {
    for (const layer of this.layers) {
      if ("uAudioLow" in layer.material.uniforms) {
        layer.material.uniforms.uAudioLow.value = low;
      }
      if ("uAudioMid" in layer.material.uniforms) {
        layer.material.uniforms.uAudioMid.value = mid;
      }
      if ("uAudioHigh" in layer.material.uniforms) {
        layer.material.uniforms.uAudioHigh.value = high;
      }
    }
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.timeline?.kill();
    this.clearEnterTimeout();
    window.cancelAnimationFrame(this.animationFrameId);
    this.container.removeEventListener("pointermove", this.onPointerMove);
    this.container.removeEventListener("pointerdown", this.onPointerDown);
    this.container.removeEventListener("pointercancel", this.onPointerCancel);
    this.container.removeEventListener("wheel", this.onWheel);
    window.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("keyup", this.onKeyUp);
    window.removeEventListener("pointerup", this.onPointerUp);
    window.removeEventListener("resize", this.resize);

    for (const layer of this.layers) {
      this.scene.remove(layer.object);
      layer.geometry.dispose();
      layer.material.dispose();
    }

    this.interactionLayer.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private enterWithReducedMotion(): void {
    this.setState("entering");
    this.timeline?.kill();
    this.clearEnterTimeout();
    this.timeline = gsap.timeline({
      defaults: { ease: "power2.out" },
      onComplete: () => this.completeEntry(),
    });
    this.enterTimeoutId = window.setTimeout(() => this.completeEntry(), 520);
    this.tweenLayerOpacity(["focusParticle"], 0.9, 0.2, 0);
    this.tweenUniform("uGlobalOpacity", 0.1, 0.36, 0, ["focusParticle"]);
  }

  private completeEntry(): void {
    if (this.disposed || this.state === "completed") {
      return;
    }

    this.clearEnterTimeout();
    this.timeline?.kill();
    this.setState("completed");
    this.onEnter();
  }

  private clearEnterTimeout(): void {
    if (this.enterTimeoutId === null) {
      return;
    }

    window.clearTimeout(this.enterTimeoutId);
    this.enterTimeoutId = null;
  }

  private async buildPointCloud(): Promise<void> {
    const tier = detectPerformanceTier();
    const counts = layerCountsForTier(tier, this.reducedMotion);

    try {
      this.onAssetStatusChange?.("loading");
      const loadedAsset = await loadPointCloudAsset(this.config.asset, {
        tier,
        reducedMotion: this.reducedMotion,
      });

      if (this.disposed) {
        return;
      }

      if (loadedAsset.kind === "gaussian-splat") {
        this.addGaussianSplatLayer(loadedAsset.layer);
        for (const volumeLayer of loadedAsset.volumeLayers ?? []) {
          this.addLayer(volumeLayer);
        }
        if (loadedAsset.detailLayer) {
          this.addLayer(loadedAsset.detailLayer);
        }
      } else {
        this.addLayer(loadedAsset.layer);
      }
      this.addLayer(this.createConfiguredFocusParticle());
      this.onAssetStatusChange?.("loaded");
      return;
    } catch (caught) {
      if (this.disposed) {
        return;
      }

      const message =
        caught instanceof Error
          ? caught.message
          : "点云资产无法读取，已启用备用观测场";
      this.onRenderError?.(`${message}，已启用备用观测场`);
      this.onAssetStatusChange?.("fallback");
    }

    if (!this.config.fallbackEnabled) {
      return;
    }

    for (const layer of generateFallbackPointCloudLayers(counts)) {
      this.addLayer(layer);
    }
  }

  private createConfiguredFocusParticle(): GeneratedPointCloudLayer {
    const hotspot = this.config.hotspots[0];
    if (!hotspot) {
      return fallbackFocusParticle();
    }

    return {
      ...fallbackFocusParticle(),
      positions: new Float32Array([
        hotspot.position.x,
        hotspot.position.y,
        hotspot.position.z,
      ]),
    };
  }

  private addLayer(layer: GeneratedPointCloudLayer): void {
    const geometry = new THREE.BufferGeometry();
    const baseOpacity = layerBaseOpacity(layer.name);
    geometry.setAttribute("position", new THREE.BufferAttribute(layer.positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(layer.colors, 3));
    geometry.setAttribute("aSize", new THREE.BufferAttribute(layer.sizes, 1));
    geometry.setAttribute("aAlpha", new THREE.BufferAttribute(layer.alphas, 1));
    geometry.setAttribute("aRandom", new THREE.BufferAttribute(layer.randoms, 1));
    geometry.setAttribute("aAmplitude", new THREE.BufferAttribute(layer.amplitudes, 1));

    const material = createPointCloudMaterial({
      layer,
      pixelRatio: this.pixelRatio(),
      materialConfig: this.config.material,
    });

    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    this.scene.add(points);
    this.layers.push({
      name: layer.name,
      geometry,
      material,
      object: points,
      baseOpacity,
    });
  }

  private addGaussianSplatLayer(layer: GeneratedGaussianSplatLayer): void {
    const { geometry, material, mesh } = createGaussianSplatMesh({
      layer,
      materialConfig: this.config.material,
    });
    const baseOpacity = material.uniforms.uGlobalOpacity.value as number;

    this.scene.add(mesh);
    this.layers.push({
      name: layer.name,
      geometry,
      material,
      object: mesh,
      baseOpacity,
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
      if (excluded.has(layer.name) || !(uniformName in layer.material.uniforms)) {
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
    this.cameraController.onPointerMove(event, rect, this.state === "idle");
  };

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (this.state !== "idle") {
      return;
    }

    this.cameraController.onPointerDown(event);
    this.renderer.domElement.style.cursor = "none";
    this.container.setPointerCapture?.(event.pointerId);
  };

  private readonly onPointerUp = (event: PointerEvent): void => {
    if (!this.cameraController.onPointerUp(event)) {
      return;
    }

    this.renderer.domElement.style.cursor = "none";
    this.container.releasePointerCapture?.(event.pointerId);
  };

  private readonly onPointerCancel = (event: PointerEvent): void => {
    if (!this.cameraController.onPointerCancel(event)) {
      return;
    }

    this.renderer.domElement.style.cursor = "none";
  };

  private readonly onWheel = (event: WheelEvent): void => {
    if (!this.cameraController.onWheel(event, this.state === "idle")) {
      return;
    }

    event.preventDefault();
  };

  private readonly onKeyDown = (event: KeyboardEvent): void => {
    if (this.shouldIgnoreKeyboardTarget(event.target)) {
      return;
    }

    if (!this.cameraController.onKeyDown(event, this.state === "idle")) {
      return;
    }

    event.preventDefault();
  };

  private readonly onKeyUp = (event: KeyboardEvent): void => {
    if (!this.cameraController.onKeyUp(event)) {
      return;
    }

    event.preventDefault();
  };

  private readonly resize = (): void => {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(this.pixelRatio());
    this.renderer.setSize(width, height, false);
    this.cameraController.setDesktopExplorationEnabled(
      this.isDesktopExplorationViewport(),
    );

    for (const layer of this.layers) {
      if ("uPixelRatio" in layer.material.uniforms) {
        layer.material.uniforms.uPixelRatio.value = this.pixelRatio();
      }
    }
  };

  private animate = (): void => {
    if (this.disposed) {
      return;
    }

    const elapsed = (performance.now() - this.sceneStart) / 1000;
    const now = performance.now();
    const deltaSeconds = (now - this.lastFrameTime) / 1000;
    this.lastFrameTime = now;
    for (const layer of this.layers) {
      layer.material.uniforms.uTime.value = elapsed;
    }

    if (this.state === "idle") {
      this.cameraController.updateIdle(elapsed, deltaSeconds);
      this.notifyCameraPosition(false);
    }

    this.cameraController.lookAtTarget();
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
    return Math.min(window.devicePixelRatio || 1, 1.25);
  }

  private isDesktopExplorationViewport(): boolean {
    if (typeof window === "undefined") {
      return false;
    }

    return window.matchMedia("(min-width: 768px) and (hover: hover) and (pointer: fine)").matches;
  }

  private shouldIgnoreKeyboardTarget(target: EventTarget | null): boolean {
    const element = target as HTMLElement | null;
    if (!element) {
      return false;
    }

    return (
      element.isContentEditable ||
      element.tagName === "INPUT" ||
      element.tagName === "TEXTAREA" ||
      element.tagName === "SELECT" ||
      element.tagName === "BUTTON"
    );
  }

  private notifyCameraPosition(force: boolean): void {
    if (!this.onCameraPositionChange) {
      return;
    }

    const now = performance.now();
    if (!force && now - this.lastCameraPositionNotify < 100) {
      return;
    }

    this.lastCameraPositionNotify = now;
    this.onCameraPositionChange(this.cameraController.position);
  }
}
