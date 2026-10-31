import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Object3D } from "three";
import type { InstancedMesh, ShaderMaterial } from "three";
import type { SceneClock } from "./life";
import type { Weather } from "./motion";

const vertexShader = `
  uniform float time;
  uniform float speed;
  uniform float wind;
  attribute float tip;
  varying float fade;
  void main() {
    float y = mod(position.y - time * speed, 180.0);
    vec3 p = vec3(position.x + (180.0-y)*wind, y, position.z);
    p += tip * vec3(-wind*5.0, 5.0, 0.0);
    vec4 viewPosition = modelViewMatrix * vec4(p,1.0);
    fade = clamp(1.0-length(viewPosition.xyz)/850.0, .12, 1.0);
    gl_Position = projectionMatrix * viewPosition;
  }
`;
const fragmentShader = `
  uniform float opacity;
  varying float fade;
  void main() {
    gl_FragColor = vec4(.75,.83,.89,opacity*fade);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

/** Seed once; every drop moves in the vertex shader. One draw call, no CPU uploads. */
export function Rain({
  clock,
  weather,
  count,
  reducedMotion,
}: {
  clock: SceneClock;
  weather: Weather;
  count: number;
  reducedMotion: boolean;
}) {
  const material = useRef<ShaderMaterial>(null);
  const buffers = useMemo(() => {
    const positions = new Float32Array(count * 6),
      tips = new Float32Array(count * 2);
    let seed = 2049;
    const random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    for (let i = 0; i < count; i++) {
      const x = (random() - 0.5) * 850,
        y = random() * 180,
        z = (random() - 0.5) * 650 - 80;
      positions.set([x, y, z, x, y, z], i * 6);
      tips.set([0, 1], i * 2);
    }
    return { positions, tips };
  }, [count]);
  const uniforms = useMemo(
    () => ({
      time: { value: 0 },
      speed: { value: weather === "storm" ? 95 : 65 },
      wind: { value: weather === "storm" ? 0.13 : 0.055 },
      opacity: { value: weather === "storm" ? 0.55 : 0.4 },
    }),
    [weather],
  );
  useFrame(() => {
    if (material.current) material.current.uniforms.time.value = clock.current;
  });
  return (
    <lineSegments
      visible={weather !== "clear" && !reducedMotion}
      frustumCulled={false}
      raycast={() => {}}
      name="rain-particles"
    >
      <bufferGeometry key={count}>
        <bufferAttribute
          attach="attributes-position"
          args={[buffers.positions, 3]}
        />
        <bufferAttribute attach="attributes-tip" args={[buffers.tips, 1]} />
      </bufferGeometry>
      <shaderMaterial
        ref={material}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </lineSegments>
  );
}

export const weatherLighting = {
  clear: {
    background: "#8c9393",
    fog: "#9ba2a3",
    near: 500,
    far: 1300,
    sun: 2,
    ambient: 0.9,
  },
  rain: {
    background: "#7d8a93",
    fog: "#8999a6",
    near: 320,
    far: 1000,
    sun: 1.15,
    ambient: 1.15,
  },
  storm: {
    background: "#697a88",
    fog: "#7b8f9f",
    near: 240,
    far: 850,
    sun: 0.7,
    ambient: 1.1,
  },
};

export function Puddles({ wet }: { wet: boolean }) {
  const mesh = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    if (!mesh.current) return;
    const object = new Object3D();
    for (let i = 0; i < 18; i++) {
      object.position.set(-220 + ((i * 73) % 440), 0.06, 64 + ((i * 19) % 45));
      object.rotation.set(-Math.PI / 2, 0, i * 0.7);
      object.scale.set(3 + (i % 4) * 2, 1.4 + (i % 3), 1);
      object.updateMatrix();
      mesh.current.setMatrixAt(i, object.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    mesh.current.computeBoundingSphere();
  }, []);
  return (
    <instancedMesh
      ref={mesh}
      args={[undefined, undefined, 18]}
      visible={wet}
      raycast={() => {}}
    >
      <circleGeometry args={[1, 20]} />
      <meshStandardMaterial
        color="#627d8e"
        transparent
        opacity={0.34}
        roughness={0.18}
        metalness={0.45}
        depthWrite={false}
      />
    </instancedMesh>
  );
}
