import * as THREE from "three";

import type { PointCloudHotspot } from "./types";

export class PointCloudInteractionLayer {
  private readonly hotspots: PointCloudHotspot[];

  constructor(hotspots: PointCloudHotspot[]) {
    this.hotspots = hotspots;
  }

  nearestHotspot(point: THREE.Vector3): PointCloudHotspot | null {
    let nearest: PointCloudHotspot | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;

    for (const hotspot of this.hotspots) {
      const distance = point.distanceTo(
        new THREE.Vector3(
          hotspot.position.x,
          hotspot.position.y,
          hotspot.position.z,
        ),
      );
      if (distance <= hotspot.radius && distance < nearestDistance) {
        nearest = hotspot;
        nearestDistance = distance;
      }
    }

    return nearest;
  }

  dispose(): void {
    this.hotspots.length = 0;
  }
}
