import { useEffect, useLayoutEffect, useMemo } from "react";
import { MeshStandardNodeMaterial } from "three/webgpu";
import {
  color,
  float,
  mix,
  mx_noise_float,
  normalMap,
  positionWorld,
  smoothstep,
  texture,
  uniform,
  vec2,
  vec3,
} from "three/tsl";
import { useSurfaceTextures } from "./surface-textures";
import { concourses } from "./scenery-layout";

/** Photographic microdetail plus world-scale slabs, wear and local wetness. */
export function ApronMaterial({ wet }: { wet: boolean }) {
  const maps = useSurfaceTextures();
  const { material, moisture } = useMemo(() => {
    const material = new MeshStandardNodeMaterial();
    const moisture = uniform(0);
    const uv = positionWorld.xz.div(6);
    const grain = texture(maps.concrete, uv).rgb.dot(
      vec3(0.2126, 0.7152, 0.0722),
    );
    const slabUV = positionWorld.xz.div(9);
    const cell = slabUV.floor();
    const slabTone = mx_noise_float(vec3(cell.x, 0, cell.y))
      .mul(0.035)
      .add(0.96);
    const edge = slabUV.fract().sub(0.5).abs();
    const aa = slabUV.fwidth().max(vec2(0.002));
    const joints = smoothstep(vec2(0.5).sub(aa), vec2(0.5), edge);
    const joint = joints.x.max(joints.y);
    const stains = mx_noise_float(positionWorld.mul(0.075)).mul(0.5).add(0.5);
    const damp = smoothstep(0.42, 0.72, stains).mul(moisture);
    const concrete = mix(
      color("#6a6e6d"),
      color("#898c89"),
      grain.mul(2).clamp(0, 1),
    );
    material.colorNode = concrete
      .mul(slabTone)
      .mul(mix(1, 0.8, joint))
      .mul(mix(1, 0.76, damp));
    material.roughnessNode = mix(
      texture(maps.roughness, uv).r.mul(0.3).add(0.65),
      0.33,
      damp,
    );
    material.normalNode = normalMap(texture(maps.normal, uv), vec2(0.2));
    // Local ambient occlusion around the terminal, without a screen-space pass.
    let occlusion = float(1).mul(1);
    for (const concourse of concourses) {
      const half = concourse.rotation
        ? vec2(8.75, concourse.length / 2 + 8.75)
        : vec2(concourse.length / 2 + 8.75, 8.75);
      const distance = positionWorld.xz
        .sub(vec2(concourse.position[0], concourse.position[2]))
        .abs()
        .sub(half)
        .max(vec2(0))
        .length();
      occlusion = occlusion.mul(smoothstep(0, 6, distance).mul(0.4).add(0.6));
    }
    material.aoNode = occlusion;
    material.metalness = 0;
    material.envMapIntensity = 0.65;
    return { material, moisture };
  }, [maps]);
  useLayoutEffect(() => {
    moisture.value = wet ? 1 : 0;
  }, [wet, moisture]);
  useEffect(() => () => material.dispose(), [material]);
  return <primitive object={material} attach="material" />;
}
