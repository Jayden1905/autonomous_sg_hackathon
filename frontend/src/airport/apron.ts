import {
  DataTexture,
  RepeatWrapping,
  LinearMipmapLinearFilter,
  LinearFilter,
  RGBAFormat,
} from "three";

/** Deterministic concrete grain and joints; mipmaps keep distant slabs quiet. */
export function apronTexture() {
  const size = 256;
  const pixels = new Uint8Array(size * size * 4);
  let seed = 41;
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      const value = x < 1 || y < 1 ? 173 : 235 + (seed % 14);
      const offset = (y * size + x) * 4;
      pixels.set([value, value, value, 255], offset);
    }
  const texture = new DataTexture(pixels, size, size, RGBAFormat);
  texture.wrapS = texture.wrapT = RepeatWrapping;
  texture.repeat.set(120, 30);
  texture.generateMipmaps = true;
  texture.minFilter = LinearMipmapLinearFilter;
  texture.magFilter = LinearFilter;
  texture.needsUpdate = true;
  return texture;
}
