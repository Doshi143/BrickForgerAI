"use client";

/**
 * three.js LDraw viewer, ported from the repo's standalone
 * `viewer/index.html` (Phase 0) rather than rebuilt: same LDrawLoader, same
 * OrbitControls setup, same `ldcfgalt.ldr` color preload (which is what
 * makes real LDraw color codes render as their actual brick colors), same
 * -Y-up handling. The only real change is that the model URL arrives as a
 * prop instead of a `?model=` query string.
 */

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { LDrawLoader } from "three/examples/jsm/loaders/LDrawLoader.js";
import { LDrawConditionalLineMaterial } from "three/examples/jsm/materials/LDrawConditionalLineMaterial.js";

const PARTS_LIBRARY_PATH =
  "https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/complete/ldraw/";
const COLORS_PATH =
  "https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/colors/ldcfgalt.ldr";

export default function Viewer3D({
  src,
  height = 520,
  background = "#1b1d21",
  onRendered,
}: {
  src: string;
  height?: number;
  background?: string;
  /** Called once, shortly after the model first renders, with a
   * data:image/png;base64 screenshot of the canvas -- used to capture a
   * real gallery thumbnail of the actual brick model (see the results
   * page, which uploads this to the backend). */
  onRendered?: (dataUrl: string) => void;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState("Loading model…");
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let disposed = false;
    let frameId = 0;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(background);

    const camera = new THREE.PerspectiveCamera(
      45,
      mount.clientWidth / mount.clientHeight,
      1,
      10000
    );
    camera.position.set(300, -260, 300);

    // preserveDrawingBuffer: the onRendered screenshot capture below reads
    // the canvas via toDataURL() right after a render call -- without this
    // flag the buffer can already be cleared by the time that read happens.
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, -60, 0);
    controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(200, -400, 300); // "above", in LDraw's -Y-up space
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.4);
    fill.position.set(-200, 100, -200);
    scene.add(fill);

    function frameObject(object3d: THREE.Object3D) {
      const box = new THREE.Box3().setFromObject(object3d);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      const dist = maxDim * 1.8;
      camera.position.set(center.x + dist, center.y - dist, center.z + dist);
      controls.target.copy(center);
      camera.near = dist / 100;
      camera.far = dist * 100;
      camera.updateProjectionMatrix();
      controls.update();
    }

    const loader = new LDrawLoader();
    loader.smoothNormals = true;
    loader.setConditionalLineMaterial(LDrawConditionalLineMaterial as never);
    loader.setPartsLibraryPath(PARTS_LIBRARY_PATH);

    loader
      .preloadMaterials(COLORS_PATH)
      .then(() => {
        if (disposed) return;
        loader.load(
          src,
          (group: THREE.Group) => {
            if (disposed) return;
            group.rotation.x = Math.PI; // LDraw is -Y-up; flip to read as +Y-up
            scene.add(group);
            frameObject(group);
            let n = 0;
            group.traverse((o) => {
              if ((o as THREE.Mesh).isMesh) n++;
            });
            setStatus(`${n.toLocaleString()} rendered pieces`);

            if (onRendered) {
              // Deliberately NOT wrapped in requestAnimationFrame: rAF is
              // throttled/suspended entirely for a hidden/background tab
              // (confirmed while testing this -- a captured screenshot
              // silently never happened, document.hidden was true), and
              // a real user opening the results page in a background tab
              // hits the exact same thing. An explicit synchronous render
              // call, right after the camera/group are already updated
              // above, gets a fresh frame into the (preserveDrawingBuffer)
              // canvas without depending on the compositor at all.
              renderer.render(scene, camera);
              onRendered(renderer.domElement.toDataURL("image/png"));
            }
          },
          undefined,
          (err: unknown) => {
            if (disposed) return;
            setIsError(true);
            setStatus(`Failed to load model: ${(err as Error)?.message ?? err}`);
          }
        );
      })
      .catch((err: unknown) => {
        if (disposed) return;
        setIsError(true);
        setStatus(`Failed to load LDraw colors: ${(err as Error)?.message ?? err}`);
      });

    function onResize() {
      if (!mount) return;
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    }
    window.addEventListener("resize", onResize);

    function animate() {
      frameId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [src, background]);

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={mountRef}
        style={{ width: "100%", height, borderRadius: 16, overflow: "hidden" }}
      />
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          padding: "6px 12px",
          borderRadius: 8,
          fontSize: 13,
          background: "rgba(0,0,0,0.5)",
          color: isError ? "#ff9b9b" : "#d8e2f0",
        }}
      >
        {status}
      </div>
    </div>
  );
}
