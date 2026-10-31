import { useLayoutEffect } from "react";
import { useThree } from "@react-three/fiber";
import {
  color,
  float,
  mix,
  positionWorld,
  texture,
  vec3,
  smoothstep,
  mx_noise_float,
} from "three/tsl";
import { materials } from "./geometry";
import { useSurfaceTextures } from "./surface-textures";

export function SurfaceLibrary() {
  const maps = useSurfaceTextures();
  const { invalidate, gl } = useThree();
  useLayoutEffect(() => {
    const grain = texture(maps.asphalt, positionWorld.xz.div(7)).rgb.dot(
      vec3(0.2126, 0.7152, 0.0722),
    );
    // Restrained touchdown wear on the illustrative runways, fading into the asphalt.
    let rubber = float(0).mul(1);
    for (const z of [-158, -218]) {
      const lane = positionWorld.z.sub(z).abs();
      const tracks = smoothstep(0.5, 1.1, lane).mul(
        float(1).sub(smoothstep(2.4, 3.7, lane)),
      );
      const length = smoothstep(65, 110, positionWorld.x.abs()).mul(
        float(1).sub(smoothstep(170, 205, positionWorld.x.abs())),
      );
      rubber = rubber.add(tracks.mul(length));
    }
    const wear = mx_noise_float(positionWorld.mul(vec3(0.18, 1, 4)))
      .mul(0.5)
      .add(0.5);
    materials.asphalt.colorNode = mix(
      color("#292e30"),
      color("#53595a"),
      grain.mul(2).clamp(0, 1),
    ).mul(float(1).sub(rubber.mul(wear).mul(0.3)));
    materials.asphalt.roughnessNode = grain.mul(0.18).add(0.8);
    materials.asphalt.needsUpdate = true;
    gl.shadowMap.needsUpdate = true;
    invalidate();
  }, [maps, gl, invalidate]);
  return null;
}
