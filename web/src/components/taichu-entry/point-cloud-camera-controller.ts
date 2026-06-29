import { gsap } from "gsap";
import * as THREE from "three";

import type {
  PointCloudCameraPose,
  PointCloudExplorationConfig,
  Vec3,
} from "./types";

type CameraControllerOptions = {
  camera: THREE.PerspectiveCamera;
  cameraTarget: Vec3;
  reducedMotion: boolean;
  cameraNav: PointCloudCameraPose;
  exploration: PointCloudExplorationConfig;
  desktopExplorationEnabled: boolean;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function vec3From(point: Vec3): THREE.Vector3 {
  return new THREE.Vector3(point.x, point.y, point.z);
}

export class PointCloudCameraController {
  private readonly camera: THREE.PerspectiveCamera;
  private readonly cameraTarget: Vec3;
  private readonly reducedMotion: boolean;
  private readonly cameraNav: PointCloudCameraPose;
  private pointerX = 0;
  private pointerY = 0;
  private activePointerId: number | null = null;
  private dragStartX = 0;
  private dragStartY = 0;
  private currentYaw = 0;
  private currentPitch = -0.03;
  private targetYaw = 0;
  private targetPitch = -0.03;

  constructor(options: CameraControllerOptions) {
    this.camera = options.camera;
    this.cameraTarget = options.cameraTarget;
    this.reducedMotion = options.reducedMotion;
    this.cameraNav = options.cameraNav;
    this.applyPose(options.cameraNav);
  }

  get activePointer(): number | null {
    return this.activePointerId;
  }

  get position(): Vec3 {
    return {
      x: this.camera.position.x,
      y: this.camera.position.y,
      z: this.camera.position.z,
    };
  }

  applyPose(pose: PointCloudCameraPose): void {
    this.camera.position.set(pose.position.x, pose.position.y, pose.position.z);
    this.cameraTarget.x = pose.target.x;
    this.cameraTarget.y = pose.target.y;
    this.cameraTarget.z = pose.target.z;
    this.camera.fov = pose.fov;
    this.camera.updateProjectionMatrix();
    this.syncYawPitchFromPose(pose);
    this.lookAtTarget();
  }

  tweenTo(
    timeline: gsap.core.Timeline,
    pose: PointCloudCameraPose,
    duration: number,
    position: number,
  ): void {
    timeline.to(
      this.camera.position,
      {
        x: pose.position.x,
        y: pose.position.y,
        z: pose.position.z,
        duration,
      },
      position,
    );
    timeline.to(
      this.cameraTarget,
      {
        x: pose.target.x,
        y: pose.target.y,
        z: pose.target.z,
        duration,
      },
      position,
    );
    timeline.to(
      this.camera,
      {
        fov: pose.fov,
        duration,
        onUpdate: () => this.camera.updateProjectionMatrix(),
      },
      position,
    );
  }

  setDesktopExplorationEnabled(_enabled: boolean): void {
    void _enabled;
    // The entry view uses fixed-point observation; viewport changes do not enable flight.
  }

  onKeyDown(_event: KeyboardEvent, _idle: boolean): boolean {
    void _event;
    void _idle;
    return false;
  }

  onKeyUp(_event: KeyboardEvent): boolean {
    void _event;
    return false;
  }

  onWheel(_event: WheelEvent, _idle: boolean): boolean {
    void _event;
    void _idle;
    return false;
  }

  onPointerMove(event: PointerEvent, rect: DOMRect, idle: boolean): void {
    this.pointerX = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    this.pointerY = ((event.clientY - rect.top) / rect.height - 0.5) * 2;

    if (this.activePointerId !== event.pointerId || !idle) {
      return;
    }

    const dx = event.clientX - this.dragStartX;
    const dy = event.clientY - this.dragStartY;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;

    this.targetYaw -= dx * 0.0022;
    this.targetPitch = clamp(this.targetPitch + dy * 0.0015, -0.66, 0.56);
  }

  onPointerDown(event: PointerEvent): void {
    this.activePointerId = event.pointerId;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
  }

  onPointerUp(event: PointerEvent): boolean {
    if (this.activePointerId !== event.pointerId) {
      return false;
    }

    this.activePointerId = null;
    return true;
  }

  onPointerCancel(event: PointerEvent): boolean {
    return this.onPointerUp(event);
  }

  updateIdle(elapsed: number, _deltaSeconds: number): void {
    void _deltaSeconds;
    this.updateObservation(elapsed);
  }

  lookAtTarget(): void {
    this.camera.lookAt(
      this.cameraTarget.x,
      this.cameraTarget.y,
      this.cameraTarget.z,
    );
  }

  private updateObservation(elapsed: number): void {
    const yawLerp = this.activePointerId === null ? 0.09 : 0.16;
    const pitchLerp = this.activePointerId === null ? 0.1 : 0.17;
    this.currentYaw += (this.targetYaw - this.currentYaw) * yawLerp;
    this.currentPitch += (this.targetPitch - this.currentPitch) * pitchLerp;

    const autoYaw = this.reducedMotion ? 0 : Math.sin(elapsed * 0.045) * 0.012;
    const hoverYaw = this.activePointerId === null ? this.pointerX * 0.004 : 0;
    const hoverPitch = this.activePointerId === null ? -this.pointerY * 0.003 : 0;
    const yaw = this.currentYaw + autoYaw + hoverYaw;
    const pitch = clamp(this.currentPitch + hoverPitch, -0.68, 0.58);
    const direction = this.directionFor(yaw, pitch);
    const breathe = this.reducedMotion ? 0 : Math.sin(elapsed * 0.16) * 0.1;

    this.camera.position.x +=
      (this.cameraNav.position.x - this.camera.position.x) * 0.08;
    this.camera.position.y +=
      (this.cameraNav.position.y + breathe - this.camera.position.y) * 0.08;
    this.camera.position.z +=
      (this.cameraNav.position.z - this.camera.position.z) * 0.08;

    this.cameraTarget.x = this.camera.position.x + direction.x * 390;
    this.cameraTarget.y = this.camera.position.y + direction.y * 390;
    this.cameraTarget.z = this.camera.position.z + direction.z * 390;
  }

  private directionFor(yaw: number, pitch: number): THREE.Vector3 {
    const cosPitch = Math.cos(pitch);
    return new THREE.Vector3(
      Math.sin(yaw) * cosPitch,
      Math.sin(pitch),
      Math.cos(yaw) * cosPitch,
    ).normalize();
  }

  private syncYawPitchFromPose(pose: PointCloudCameraPose): void {
    const direction = vec3From(pose.target).sub(vec3From(pose.position)).normalize();
    const yaw = Math.atan2(direction.x, direction.z);
    const pitch = Math.asin(clamp(direction.y, -1, 1));
    this.currentYaw = yaw;
    this.targetYaw = yaw;
    this.currentPitch = clamp(pitch, -0.66, 0.56);
    this.targetPitch = this.currentPitch;
  }
}
