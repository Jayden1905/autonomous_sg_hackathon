import { useEffect, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import {
  Color,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  Vector2,
  WebGLRenderTarget,
} from "three";

const quadVertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const blurFragment = `uniform sampler2D source; uniform vec2 stepSize; varying vec2 vUv;
void main(){float a=texture2D(source,vUv).a*.227027;
 a+=(texture2D(source,vUv+stepSize*1.384615).a+texture2D(source,vUv-stepSize*1.384615).a)*.316216;
 a+=(texture2D(source,vUv+stepSize*3.230769).a+texture2D(source,vUv-stepSize*3.230769).a)*.070270;
 gl_FragColor=vec4(0.,0.,0.,a);}`;

/** Bake only stationary aircraft silhouettes; never leave shadows behind moving traffic. */
export function AircraftShadows({
  revision,
  eco,
}: {
  revision: string;
  eco: boolean;
}) {
  const { gl, scene } = useThree();
  const bake = useMemo(() => {
    const resolution = eco ? 256 : 512;
    const target = new WebGLRenderTarget(resolution, resolution);
    const temp = new WebGLRenderTarget(resolution, resolution);
    const camera = new OrthographicCamera(-170, 170, 135, -135, 0.1, 45);
    camera.position.set(0, 30, 0);
    camera.up.set(0, 0, -1);
    camera.lookAt(0, 0, 0);
    const material = new ShaderMaterial({
      vertexShader: `varying float height;void main(){vec4 p=modelMatrix*vec4(position,1.);height=p.y;gl_Position=projectionMatrix*viewMatrix*p;}`,
      fragmentShader: `varying float height;void main(){gl_FragColor=vec4(0.,0.,0.,clamp(1.-height/15.,0.,1.));}`,
    });
    const blur = new ShaderMaterial({
      vertexShader: quadVertex,
      fragmentShader: blurFragment,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        source: { value: target.texture },
        stepSize: { value: new Vector2() },
      },
    });
    const quad = new Mesh(new PlaneGeometry(2, 2), blur);
    quad.frustumCulled = false;
    const copy = new Scene();
    return {
      target,
      temp,
      camera,
      material,
      blur,
      quad,
      copy,
      resolution,
      revision: "",
    };
  }, [eco]);
  useFrame(() => {
    if (bake.revision === revision) return;
    scene.updateMatrixWorld(true);
    scene.traverse((root) => {
      if (root.name !== "parked-aircraft") return;
      root.traverse((object) => {
        if (!(object instanceof Mesh)) return;
        const clone = new Mesh(object.geometry, bake.material);
        clone.matrixAutoUpdate = false;
        clone.matrix.copy(object.matrixWorld);
        bake.copy.add(clone);
      });
    });
    const previous = gl.getRenderTarget();
    const clear = gl.getClearColor(new Color()),
      alpha = gl.getClearAlpha();
    try {
      gl.setClearColor(0, 0);
      gl.setRenderTarget(bake.target);
      gl.clear();
      gl.render(bake.copy, bake.camera);
      bake.blur.uniforms.source.value = bake.target.texture;
      bake.blur.uniforms.stepSize.value.set(1.4 / bake.resolution, 0);
      gl.setRenderTarget(bake.temp);
      gl.clear();
      gl.render(bake.quad, bake.camera);
      bake.blur.uniforms.source.value = bake.temp.texture;
      bake.blur.uniforms.stepSize.value.set(0, 1.4 / bake.resolution);
      gl.setRenderTarget(bake.target);
      gl.clear();
      gl.render(bake.quad, bake.camera);
      bake.revision = revision;
    } finally {
      bake.copy.clear();
      gl.setRenderTarget(previous);
      gl.setClearColor(clear, alpha);
    }
  });
  useEffect(
    () => () => {
      bake.target.dispose();
      bake.temp.dispose();
      bake.material.dispose();
      bake.blur.dispose();
      bake.quad.geometry.dispose();
    },
    [bake],
  );
  return (
    <mesh position={[0, 0.045, 0]} rotation-x={-Math.PI / 2} raycast={() => {}}>
      <planeGeometry args={[340, 270]} />
      <meshBasicMaterial
        map={bake.target.texture}
        transparent
        opacity={0.38}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
