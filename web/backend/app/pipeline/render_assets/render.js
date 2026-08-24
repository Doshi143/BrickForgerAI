/**
 * Headless step renderer for build-instruction PDFs. Loaded by Playwright
 * (see ../instructions_pdf.py) in a headless Chromium page -- NOT part of
 * the Next.js frontend build, deliberately a standalone page so the
 * Python worker can drive it with zero Node/bundler dependency.
 *
 * Reuses the exact three.js/LDrawLoader setup already proven in
 * web/frontend/components/Viewer3D.tsx (same parts-library CDN mirror,
 * same missing-parts overrides, same -Y-up flip, same preserveDrawingBuffer
 * capture trick) rather than inventing a second rendering approach --
 * DESIGN.md's own "### Instructions" section calls sharing one code path
 * between the interactive viewer and the PDF export "a big saving".
 *
 * The one genuinely new piece: instead of loading a plain model.ldr, this
 * loads a *stepped* LDR (brickforge.pipeline.instructions.stepped_ldr_text)
 * that carries real LDraw `0 STEP` markers between layers. LDrawLoader's
 * own computeBuildingSteps() (a real, standard part of the loader, not a
 * BrickForgerAI addition) tags every parsed part-group with
 * userData.buildingStep -- confirmed by reading LDrawLoader.js directly:
 * each top-level `1 <colour> ...` line in a flat (non-MPD) file becomes
 * its own Group via loadModel(), and that Group inherits
 * subobject.startingBuildingStep from whichever `0 STEP` line preceded it
 * in the source text. That's what showStepAndCapture below toggles
 * visibility on.
 */
import * as THREE from "three";
import { LDrawLoader } from "three/addons/loaders/LDrawLoader.js";
import { LDrawConditionalLineMaterial } from "three/addons/materials/LDrawConditionalLineMaterial.js";

const PARTS_LIBRARY_PATH =
  "https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/complete/ldraw/";
const COLORS_PATH =
  "https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/colors/ldcfgalt.ldr";

// Same 2 parts (7825/7835, the 1x3/1x4 "cheese" slopes) missing from the
// CDN mirror as Viewer3D.tsx documents -- served locally here instead of
// from the Next.js frontend's /public, since this page isn't part of that
// app. See ./ldraw-overrides/ (copied from web/frontend/public/ldraw-overrides
// at the same commit that added them there).
const MISSING_PARTS_OVERRIDES = {
  "parts/7825.dat": "./ldraw-overrides/parts/7825.dat",
  "parts/7835.dat": "./ldraw-overrides/parts/7835.dat",
  "parts/s/7825s01.dat": "./ldraw-overrides/parts/s/7825s01.dat",
  "parts/s/7825s02.dat": "./ldraw-overrides/parts/s/7825s02.dat",
  "parts/s/7825s03.dat": "./ldraw-overrides/parts/s/7825s03.dat",
  "parts/s/7835s01.dat": "./ldraw-overrides/parts/s/7835s01.dat",
  "parts/s/7835s02.dat": "./ldraw-overrides/parts/s/7835s02.dat",
};

const HIGHLIGHT_COLOR = 0xffdd33;

let scene, camera, renderer, loader;
let rootGroup = null;
let highlightHelper = null;

function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color("#1b1d21");

  camera = new THREE.PerspectiveCamera(45, 1000 / 800, 1, 10000);
  camera.position.set(300, -260, 300);

  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(1000, 800);
  document.getElementById("mount").appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const key = new THREE.DirectionalLight(0xffffff, 1.2);
  key.position.set(200, -400, 300);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.4);
  fill.position.set(-200, 100, -200);
  scene.add(fill);

  loader = new LDrawLoader();
  loader.smoothNormals = true;
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  loader.setPartsLibraryPath(PARTS_LIBRARY_PATH);
  loader.manager.setURLModifier((url) => {
    for (const suffix in MISSING_PARTS_OVERRIDES) {
      if (url.endsWith(suffix)) return MISSING_PARTS_OVERRIDES[suffix];
    }
    return url;
  });

  return loader.preloadMaterials(COLORS_PATH);
}

/** Every Group LDrawLoader creates for a real part placement gets a
 * userData.buildingStep (see module docstring) -- but so do any nested
 * Groups inside that part's own subfile, inheriting the same value. Both
 * `visible` and the highlight-box pass below tolerate that redundancy:
 * setting the same visibility/expanding the same bounds twice is a no-op,
 * not a bug. */
function forEachStepGroup(callback) {
  rootGroup.traverse((c) => {
    if (c.isGroup && typeof c.userData.buildingStep === "number") {
      callback(c);
    }
  });
}

window.__bf = {
  ready: false,

  async boot() {
    await init();
    this.ready = true;
  },

  /** Parses stepped LDR text (see instructions.py::stepped_ldr_text) once.
   * Returns the total number of build steps found. */
  loadStepped(text) {
    return new Promise((resolve, reject) => {
      loader.parse(
        text,
        (group) => {
          group.rotation.x = Math.PI; // LDraw is -Y-up; flip to +Y-up, same as Viewer3D.tsx
          scene.add(group);
          rootGroup = group;
          resolve(group.userData.numBuildingSteps ?? 1);
        },
        (err) => reject(err)
      );
    });
  },

  /** Fit the camera to the FULL model once, so every step's screenshot
   * shares one consistent framing rather than zooming/panning per step. */
  frameAll() {
    const box = new THREE.Box3().setFromObject(rootGroup);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const dist = maxDim * 1.8;
    camera.position.set(center.x + dist, center.y - dist, center.z + dist);
    camera.lookAt(center);
    camera.near = dist / 100;
    camera.far = dist * 100;
    camera.updateProjectionMatrix();
  },

  /** Shows every part placed at step <= stepIndex, hides everything after
   * it, draws a highlight box around just this step's new parts, renders,
   * and returns a data:image/png;base64 URL of the result -- captured via
   * toDataURL right after an explicit render() call (not a screenshot of
   * the composited page), the same proven trick Viewer3D.tsx already uses
   * for its own gallery-thumbnail capture, since headless Chromium has no
   * compositor loop to reliably screenshot otherwise. */
  showStepAndCapture(stepIndex) {
    if (highlightHelper) {
      scene.remove(highlightHelper);
      highlightHelper.geometry.dispose();
      highlightHelper.material.dispose();
      highlightHelper = null;
    }

    const newBox = new THREE.Box3();
    let sawNew = false;
    forEachStepGroup((c) => {
      c.visible = c.userData.buildingStep <= stepIndex;
      if (c.userData.buildingStep === stepIndex && c.visible) {
        newBox.expandByObject(c);
        sawNew = true;
      }
    });

    if (sawNew) {
      highlightHelper = new THREE.Box3Helper(newBox, new THREE.Color(HIGHLIGHT_COLOR));
      scene.add(highlightHelper);
    }

    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  },
};
