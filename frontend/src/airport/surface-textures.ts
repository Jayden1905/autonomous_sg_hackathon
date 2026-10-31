import { useMemo } from "react";
import { useLoader } from "@react-three/fiber";
import { RepeatWrapping, SRGBColorSpace, TextureLoader } from "three";

const paths = [
  "concrete-color.jpg",
  "concrete-normal.jpg",
  "concrete-roughness.jpg",
  "asphalt-color.jpg",
].map((name) => `/materials/${name}`);

/** Shared 1K maps, loaded from this deployment rather than a runtime CDN. */
export function useSurfaceTextures() {
  const maps = useLoader(TextureLoader, paths);
  return useMemo(() => {
    maps.forEach((map, i) => {
      map.wrapS = map.wrapT = RepeatWrapping;
      map.anisotropy = 4;
      if (i === 0 || i === 3) map.colorSpace = SRGBColorSpace;
      map.needsUpdate = true;
    });
    return {
      concrete: maps[0],
      normal: maps[1],
      roughness: maps[2],
      asphalt: maps[3],
    };
  }, [maps]);
}
