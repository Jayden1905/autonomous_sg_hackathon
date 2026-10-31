import { MeshStandardNodeMaterial } from "three/webgpu";
import {
  color,
  mix,
  positionWorld,
  vec2,
  mx_noise_float,
  smoothstep,
  bumpMap,
} from "three/tsl";

/** World-space panel seams survive terminal geometry batching. */
export function roofMaterial() {
  const material = new MeshStandardNodeMaterial();
  const panels = positionWorld.xz.div(vec2(1.6, 6));
  const edge = panels.fract().sub(0.5).abs();
  const width = panels.fwidth().max(vec2(0.006));
  const seam = smoothstep(vec2(0.5).sub(width.mul(1.2)), vec2(0.5), edge);
  const joint = seam.x.max(seam.y);
  const variation = mx_noise_float(positionWorld.mul(0.17)).mul(0.06).add(0.94);
  material.colorNode = mix(
    color("#9ba19f").mul(variation),
    color("#626c70"),
    joint.mul(0.6),
  );
  material.roughnessNode = mix(0.64, 0.88, joint);
  material.normalNode = bumpMap(joint.mul(-0.025));
  material.metalness = 0.42;
  material.envMapIntensity = 0.7;
  return material;
}

export function asphaltMaterial() {
  const material = new MeshStandardNodeMaterial();
  material.color.set("#343b3f");
  material.roughness = 0.94;
  return material;
}

export function vergeMaterial() {
  const material = new MeshStandardNodeMaterial();
  const broad = mx_noise_float(positionWorld.mul(0.035)).mul(0.5).add(0.5);
  const grain = mx_noise_float(positionWorld.mul(1.8)).mul(0.08).add(0.92);
  material.colorNode = mix(color("#30382e"), color("#444638"), broad).mul(
    grain,
  );
  material.roughness = 1;
  return material;
}
