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

/** This mirror is missing exactly 2 official parts (7825/7835, the 1x3 and
 * 1x4 "cheese" slopes -- part of catalog/parts_v1.yaml's 2-plate slope
 * family) and their subparts -- confirmed directly against the mirror's
 * repo tree, not assumed from one failed load. A model using either part
 * (a real, reproduced failure: "Subobject '7825.dat' could not be loaded")
 * otherwise fails to render entirely, since LDrawLoader has no per-file
 * fallback. Fetched the missing files from library.ldraw.org (which has
 * them, but sets session cookies and no CORS header, so the browser can't
 * fetch it directly) and self-hosted them under public/ldraw-overrides/,
 * redirected here via LoadingManager.setURLModifier -- same-origin, no
 * CORS concerns, and independent of a third-party repo's completeness. */
const MISSING_PARTS_OVERRIDES: Record<string, string> = {
  "parts/7825.dat": "/ldraw-overrides/parts/7825.dat",
  "parts/7835.dat": "/ldraw-overrides/parts/7835.dat",
  "parts/s/7825s01.dat": "/ldraw-overrides/parts/s/7825s01.dat",
  "parts/s/7825s02.dat": "/ldraw-overrides/parts/s/7825s02.dat",
  "parts/s/7825s03.dat": "/ldraw-overrides/parts/s/7825s03.dat",
  "parts/s/7835s01.dat": "/ldraw-overrides/parts/s/7835s01.dat",
  "parts/s/7835s02.dat": "/ldraw-overrides/parts/s/7835s02.dat",
};

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
    // A real bug lived here until caught from actual reported behavior
    // (previews reading as "the underside/back" of the model): after the
    // group's own `rotation.x = Math.PI` flip below (LDraw -Y-up -> world
    // +Y-up), a NEGATIVE Y camera offset puts the camera BELOW the model
    // looking UP at its underside, not above it looking down. +260, not
    // -260, is the fix -- same sign correction applied to frameObject and
    // the key light below.
    //
    // X/Z were also both flipped to negative (a second, separate reported
    // issue): the model's own front consistently faces away from a
    // positive-X/Z camera, so both the default interactive view and the
    // auto-captured thumbnail (onRendered, which fires right after
    // frameObject positions the camera -- see below) were showing the
    // back of the build. Height/elevation (the Y offset) is unaffected,
    // this is a pure 180-degree turn around the model.
    camera.position.set(-300, 260, -300);

    // preserveDrawingBuffer: the onRendered screenshot capture below reads
    // the canvas via toDataURL() right after a render call -- without this
    // flag the buffer can already be cleared by the time that read happens.
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 60, 0);
    controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(-200, 400, -300); // genuinely above, post-flip (see camera comment above); X/Z match the camera's own 180-degree turn so the now-front-facing side stays key-lit, not thrown into shadow
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.4);
    fill.position.set(200, 100, 200);
    scene.add(fill);

    function frameObject(object3d: THREE.Object3D) {
      const box = new THREE.Box3().setFromObject(object3d);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      const dist = maxDim * 1.8;
      // Negative X/Z (not positive) -- see the initial camera.position
      // comment above for why: this is what actually determines both the
      // default interactive angle and the auto-captured thumbnail for
      // every real model (this runs once the model's own real bounding
      // box is known, overriding the placeholder position set before
      // load).
      camera.position.set(center.x - dist, center.y + dist, center.z - dist);
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
    loader.manager.setURLModifier((url: string) => {
      for (const suffix in MISSING_PARTS_OVERRIDES) {
        if (url.endsWith(suffix)) return MISSING_PARTS_OVERRIDES[suffix];
      }
      return url;
    });

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
