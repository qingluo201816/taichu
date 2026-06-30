import { gsap } from "gsap";
import * as THREE from "three";

import type { ForegroundPlanetConfig, Vec3 } from "./types";

const atmosphereVertexShader = `
varying vec3 vWorldNormal;
varying vec3 vWorldPosition;

void main() {
  vec4 worldPosition = modelMatrix * vec4(position, 1.0);

  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  vWorldPosition = worldPosition.xyz;
  gl_Position = projectionMatrix * viewMatrix * worldPosition;
}
`;

const atmosphereFragmentShader = `
precision highp float;

uniform float uOpacity;

varying vec3 vWorldNormal;
varying vec3 vWorldPosition;

void main() {
  vec3 worldNormal = normalize(vWorldNormal);
  vec3 viewDirection = normalize(cameraPosition - vWorldPosition);
  float rim = pow(1.0 - max(dot(worldNormal, viewDirection), 0.0), 3.35);
  float alpha = rim * uOpacity * 0.58;

  if (alpha <= 0.004) {
    discard;
  }

  gl_FragColor = vec4(vec3(0.46, 0.56, 0.50), alpha);
}
`;

function vec3ToThree(value: Vec3): THREE.Vector3 {
  return new THREE.Vector3(value.x, value.y, value.z);
}

function addVec3(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.x + b.x,
    y: a.y + b.y,
    z: a.z + b.z,
  };
}

function warnTextureFailure(name: string, url: string): void {
  console.warn(`[太初入口] 星球贴图加载失败：${name} (${url})，已使用降级显示`);
}

function configureTexture(
  texture: THREE.Texture,
  colorSpace: THREE.ColorSpace | "",
): THREE.Texture {
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  if (colorSpace) {
    texture.colorSpace = colorSpace;
  }
  texture.needsUpdate = true;
  return texture;
}

export class ForegroundPlanet {
  readonly group = new THREE.Group();

  private readonly config: ForegroundPlanetConfig;
  private readonly reducedMotion: boolean;
  private readonly textureLoader = new THREE.TextureLoader();
  private readonly planetMesh: THREE.Mesh;
  private readonly cloudMesh: THREE.Mesh;
  private readonly atmosphereMesh: THREE.Mesh;
  private readonly atmosphereGlowMesh: THREE.Mesh;
  private readonly particleRingMesh: THREE.Mesh;
  private readonly runeCircleMesh: THREE.Mesh;
  private readonly foregroundFogMesh: THREE.Mesh;
  private readonly planetMaterial: THREE.MeshStandardMaterial;
  private readonly cloudMaterial: THREE.MeshBasicMaterial;
  private readonly atmosphereMaterial: THREE.ShaderMaterial;
  private readonly atmosphereGlowMaterial: THREE.MeshBasicMaterial;
  private readonly particleRingMaterial: THREE.MeshBasicMaterial;
  private readonly runeCircleMaterial: THREE.MeshBasicMaterial;
  private readonly foregroundFogMaterial: THREE.MeshBasicMaterial;
  private readonly textures: THREE.Texture[] = [];
  private activePosition: Vec3;
  private activeRadius: number;
  private readonly projectedCenter = new THREE.Vector3();

  constructor(config: ForegroundPlanetConfig, reducedMotion: boolean) {
    this.config = config;
    this.reducedMotion = reducedMotion;
    this.activePosition = config.position;
    this.activeRadius = config.radius;
    this.group.visible = config.enabled;
    this.group.position.copy(vec3ToThree(config.position));
    this.group.rotation.z = THREE.MathUtils.degToRad(config.tiltDegrees);
    this.group.scale.setScalar(config.radius);

    this.planetMaterial = new THREE.MeshStandardMaterial({
      color: new THREE.Color(0x17443f),
      emissive: new THREE.Color(0x1b2d1f),
      emissiveIntensity: 0.18,
      metalness: 0.02,
      opacity: config.opacity,
      roughness: 0.86,
      transparent: config.opacity < 1,
    });
    this.planetMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1, 128, 72),
      this.planetMaterial,
    );
    this.planetMesh.renderOrder = 2;

    this.cloudMaterial = new THREE.MeshBasicMaterial({
      color: new THREE.Color(0xe8e0c4),
      transparent: true,
      opacity: 0,
      depthWrite: false,
    });
    this.cloudMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1.018, 96, 56),
      this.cloudMaterial,
    );
    this.cloudMesh.visible = false;
    this.cloudMesh.renderOrder = 3;

    this.atmosphereMaterial = new THREE.ShaderMaterial({
      vertexShader: atmosphereVertexShader,
      fragmentShader: atmosphereFragmentShader,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uOpacity: { value: config.atmosphereOpacity },
      },
    });
    this.atmosphereMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1.045, 96, 56),
      this.atmosphereMaterial,
    );
    this.atmosphereMesh.renderOrder = 4;

    this.atmosphereGlowMaterial = this.createDecorMaterial();
    this.atmosphereGlowMesh = this.createDecorPlane(2.9, this.atmosphereGlowMaterial);
    this.atmosphereGlowMesh.visible = false;
    this.atmosphereGlowMesh.renderOrder = 5;
    // TODO: Replace the billboard glow with a UV-mapped atmosphere shell if the final art needs exact spherical projection.

    this.particleRingMaterial = this.createDecorMaterial();
    this.particleRingMaterial.blending = THREE.AdditiveBlending;
    this.particleRingMesh = this.createDecorPlane(3.3, this.particleRingMaterial);
    this.particleRingMesh.rotation.x = THREE.MathUtils.degToRad(64);
    this.particleRingMesh.rotation.z = THREE.MathUtils.degToRad(-18);
    this.particleRingMesh.visible = false;
    this.particleRingMesh.renderOrder = 6;

    this.runeCircleMaterial = this.createDecorMaterial();
    this.runeCircleMaterial.blending = THREE.AdditiveBlending;
    this.runeCircleMesh = this.createDecorPlane(2.42, this.runeCircleMaterial);
    this.runeCircleMesh.position.z = 0.08;
    this.runeCircleMesh.visible = false;
    this.runeCircleMesh.renderOrder = 7;

    this.foregroundFogMaterial = this.createDecorMaterial();
    this.foregroundFogMesh = this.createDecorPlane(3.4, this.foregroundFogMaterial);
    this.foregroundFogMesh.position.set(-0.12, -0.12, 0.16);
    this.foregroundFogMesh.visible = false;
    this.foregroundFogMesh.renderOrder = 8;

    this.group.add(
      this.planetMesh,
      this.cloudMesh,
      this.atmosphereMesh,
      this.atmosphereGlowMesh,
      this.particleRingMesh,
      this.runeCircleMesh,
      this.foregroundFogMesh,
    );

    this.loadTextures();
  }

  resize(width: number): void {
    const useMobileLayout = width < 640 && this.config.mobilePosition;
    this.activePosition = useMobileLayout
      ? this.config.mobilePosition ?? this.config.position
      : this.config.position;
    this.activeRadius =
      width < 640 && this.config.mobileRadius
        ? this.config.mobileRadius
        : this.config.radius;
    this.group.position.copy(vec3ToThree(this.activePosition));
    this.group.scale.setScalar(this.activeRadius);
  }

  update(
    elapsed: number,
    camera: THREE.PerspectiveCamera,
    entering: boolean,
  ): void {
    if (!this.config.enabled) {
      return;
    }

    this.updateVisibility(camera, entering);

    if (this.reducedMotion) {
      return;
    }

    this.planetMesh.rotation.y = elapsed * this.config.rotationSpeed;
    this.cloudMesh.rotation.y = elapsed * this.config.cloudRotationSpeed;
    this.particleRingMesh.rotation.z =
      THREE.MathUtils.degToRad(-18) +
      Math.sin(elapsed * 0.08) * THREE.MathUtils.degToRad(1.4);
    this.runeCircleMesh.rotation.z = -elapsed * this.config.rotationSpeed * 0.72;
    this.foregroundFogMesh.rotation.z =
      Math.sin(elapsed * 0.05) * THREE.MathUtils.degToRad(2.2);
  }

  beginEntry(timeline: gsap.core.Timeline): void {
    if (!this.config.enabled) {
      return;
    }

    if (this.reducedMotion) {
      return;
    }

    const driftTarget = addVec3(this.activePosition, this.config.enterDrift);
    timeline.to(
      this.group.position,
      {
        x: driftTarget.x,
        y: driftTarget.y,
        z: driftTarget.z,
        duration: 0.95,
        ease: "power2.out",
      },
      0.04,
    );
    timeline.to(
      this.group.rotation,
      {
        y: this.group.rotation.y + THREE.MathUtils.degToRad(18),
        duration: 0.95,
        ease: "power2.out",
      },
      0.04,
    );
    timeline.to(
      this.group.scale,
      {
        x: this.activeRadius * 1.06,
        y: this.activeRadius * 1.06,
        z: this.activeRadius * 1.06,
        duration: 0.95,
        ease: "power2.out",
      },
      0.04,
    );

    const finalStart = 3.25;
    this.tweenMaterialOpacity(timeline, this.cloudMaterial, this.config.cloudOpacity * 0.56, finalStart);
    this.tweenAtmosphereOpacity(
      timeline,
      this.config.atmosphereOpacity * 0.48,
      finalStart,
    );
    for (const material of [
      this.atmosphereGlowMaterial,
      this.particleRingMaterial,
      this.runeCircleMaterial,
      this.foregroundFogMaterial,
    ]) {
      this.tweenMaterialOpacity(
        timeline,
        material,
        Math.min(material.opacity, this.config.decorOpacity * 0.32),
        finalStart,
      );
    }
  }

  dispose(): void {
    for (const texture of this.textures) {
      texture.dispose();
    }

    this.group.traverse(object => {
      if (!(object instanceof THREE.Mesh)) {
        return;
      }
      object.geometry.dispose();
      if (Array.isArray(object.material)) {
        for (const material of object.material) {
          material.dispose();
        }
        return;
      }
      object.material.dispose();
    });
  }

  private createDecorMaterial(): THREE.MeshBasicMaterial {
    return new THREE.MeshBasicMaterial({
      color: new THREE.Color(0xd8d0b5),
      transparent: true,
      opacity: 0,
      depthWrite: false,
      depthTest: true,
      side: THREE.DoubleSide,
      blending: THREE.NormalBlending,
    });
  }

  private createDecorPlane(
    size: number,
    material: THREE.MeshBasicMaterial,
  ): THREE.Mesh {
    return new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
  }

  private loadTextures(): void {
    const paths = this.config.texturePaths;
    this.loadTexture("albedo", paths.albedo, THREE.SRGBColorSpace, texture => {
      this.planetMaterial.map = texture;
      this.planetMaterial.color.set(0xffffff);
      this.planetMaterial.needsUpdate = true;
    });
    this.loadOptionalTexture("bump", paths.bump, "", texture => {
      this.planetMaterial.bumpMap = texture;
      this.planetMaterial.bumpScale = 1.45;
      this.planetMaterial.needsUpdate = true;
    });
    this.loadOptionalTexture("roughness", paths.roughness, "", texture => {
      this.planetMaterial.roughnessMap = texture;
      this.planetMaterial.roughness = 0.92;
      this.planetMaterial.needsUpdate = true;
    });
    this.loadOptionalTexture("emission", paths.emission, THREE.SRGBColorSpace, texture => {
      this.planetMaterial.emissiveMap = texture;
      this.planetMaterial.emissive.set(0xd8d59a);
      this.planetMaterial.emissiveIntensity = 0.72;
      this.planetMaterial.needsUpdate = true;
    });
    this.loadOptionalTexture("cloud alpha", paths.cloudAlpha, "", texture => {
      this.cloudMaterial.alphaMap = texture;
      this.cloudMaterial.opacity = this.config.cloudOpacity;
      this.cloudMaterial.needsUpdate = true;
      this.cloudMesh.visible = true;
    });
    this.loadOptionalTexture(
      "atmosphere glow",
      paths.atmosphereGlow,
      THREE.SRGBColorSpace,
      texture => {
        this.atmosphereGlowMaterial.map = texture;
        this.atmosphereGlowMaterial.needsUpdate = true;
      },
    );
    this.loadOptionalTexture(
      "particle ring",
      paths.particleRing,
      THREE.SRGBColorSpace,
      texture => {
        this.particleRingMaterial.map = texture;
        this.particleRingMaterial.needsUpdate = true;
      },
    );
    this.loadOptionalTexture(
      "rune circle",
      paths.runeCircle,
      THREE.SRGBColorSpace,
      texture => {
        this.runeCircleMaterial.map = texture;
        this.runeCircleMaterial.needsUpdate = true;
      },
    );
    this.loadOptionalTexture(
      "foreground fog",
      paths.foregroundFog,
      THREE.SRGBColorSpace,
      texture => {
        this.foregroundFogMaterial.map = texture;
        this.foregroundFogMaterial.needsUpdate = true;
      },
    );
  }

  private updateVisibility(
    camera: THREE.PerspectiveCamera,
    entering: boolean,
  ): void {
    this.group.updateMatrixWorld();
    this.projectedCenter.setFromMatrixPosition(this.group.matrixWorld).project(camera);
    const edge = Math.max(
      Math.abs(this.projectedCenter.x),
      Math.abs(this.projectedCenter.y),
    );
    const inDepth = this.projectedCenter.z > -1 && this.projectedCenter.z < 1;

    this.group.visible = inDepth && edge < 1.75;
    if (entering) {
      return;
    }

    this.applyIdleOpacity(1);
  }

  private applyIdleOpacity(factor: number): void {
    this.planetMaterial.opacity = this.config.opacity * factor;
    if (this.cloudMesh.visible) {
      this.cloudMaterial.opacity = this.config.cloudOpacity * factor;
    }
    this.atmosphereMaterial.uniforms.uOpacity.value =
      this.config.atmosphereOpacity * factor;
  }

  private loadOptionalTexture(
    name: string,
    url: string | undefined,
    colorSpace: THREE.ColorSpace | "",
    onLoad: (texture: THREE.Texture) => void,
  ): void {
    if (!url) {
      return;
    }
    this.loadTexture(name, url, colorSpace, onLoad);
  }

  private loadTexture(
    name: string,
    url: string,
    colorSpace: THREE.ColorSpace | "",
    onLoad: (texture: THREE.Texture) => void,
  ): void {
    this.textureLoader.load(
      url,
      texture => {
        const configured = configureTexture(texture, colorSpace);
        this.textures.push(configured);
        onLoad(configured);
      },
      undefined,
      () => warnTextureFailure(name, url),
    );
  }

  private tweenMaterialOpacity(
    timeline: gsap.core.Timeline,
    material: THREE.MeshBasicMaterial,
    opacity: number,
    position: number,
  ): void {
    timeline.to(
      material,
      {
        opacity,
        duration: this.reducedMotion ? 0.18 : 0.62,
        ease: "power2.out",
      },
      position,
    );
  }

  private tweenAtmosphereOpacity(
    timeline: gsap.core.Timeline,
    opacity: number,
    position: number,
  ): void {
    timeline.to(
      this.atmosphereMaterial.uniforms.uOpacity,
      {
        value: opacity,
        duration: this.reducedMotion ? 0.18 : 0.62,
        ease: "power2.out",
      },
      position,
    );
  }
}
