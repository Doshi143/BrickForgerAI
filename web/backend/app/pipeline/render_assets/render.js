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

// Vertical FOV of the camera below -- used to derive the exact distance
// that fits a given bounding sphere, rather than a guessed multiplier.
// aspect > 1 (1000x800) means horizontal FOV is wider than vertical, so
// fitting on the vertical axis is the binding (safe) constraint.
const FOV_DEG = 45;
const FOV_RAD = (FOV_DEG * Math.PI) / 180;
// Breathing room around the tightest fit -- small on purpose: the whole
// point of per-step framing (see showStepAndCapture) is to fill the frame
// with whatever is actually visible at that step, not leave it looking
// like the original fixed-whole-model framing did (a small blob lost in
// a mostly-empty dark canvas -- a real, confirmed legibility problem, not
// a hypothetical one).
const FRAME_MARGIN = 1.12;
// Studs*20 LDU floor on the fitted radius, so a single first brick isn't
// zoomed in absurdly close with zero surrounding context.
const MIN_FRAME_RADIUS_LDU = 60;
// LDU padding added around the new-this-step bounding box before drawing
// the highlight, so it reads as a clear box around the new parts rather
// than a line hugging their exact edges (indistinguishable from normal
// part edges at PDF resolution).
const HIGHLIGHT_PADDING_LDU = 6;

let scene, camera, renderer, loader;
let rootGroup = null;
let highlightGroup = null;

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

  /** Fit the camera to the FULL model once -- used only as a fallback (see
   * showStepAndCapture, which frames each step dynamically instead). Kept
   * so a caller with no steps to iterate still gets a sane single frame. */
  frameAll() {
    frameBox(new THREE.Box3().setFromObject(rootGroup));
  },

  /** Shows every part placed at step <= stepIndex, hides everything after
   * it, frames the camera to fit exactly what's visible SO FAR at this
   * step (not the whole final model -- see frameBox's own docstring for
   * why a single fixed frame made most steps look like a tiny blob lost
   * in a mostly-empty canvas, a real legibility problem a user hit in
   * production, not a hypothetical), draws a highlight around just this
   * step's new parts, renders, and returns a data:image/png;base64 URL --
   * captured via toDataURL right after an explicit render() call (not a
   * screenshot of the composited page), the same proven trick
   * Viewer3D.tsx already uses for its own gallery-thumbnail capture,
   * since headless Chromium has no compositor loop to reliably screenshot
   * otherwise. */
  showStepAndCapture(stepIndex) {
    clearHighlight();

    const visibleSoFarBox = new THREE.Box3();
    const newBox = new THREE.Box3();
    let sawAny = false;
    let sawNew = false;
    forEachStepGroup((c) => {
      c.visible = c.userData.buildingStep <= stepIndex;
      if (c.visible) {
        visibleSoFarBox.expandByObject(c);
        sawAny = true;
      }
      if (c.userData.buildingStep === stepIndex && c.visible) {
        newBox.expandByObject(c);
        sawNew = true;
      }
    });

    frameBox(sawAny ? visibleSoFarBox : new THREE.Box3().setFromObject(rootGroup));

    if (sawNew) {
      newBox.expandByScalar(HIGHLIGHT_PADDING_LDU);
      highlightGroup = buildHighlight(newBox);
      scene.add(highlightGroup);
    }

    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  },
};

// Unit direction for the fixed corner viewing angle: above, front, and to
// the side -- a real bug, caught from actual rendered output (a build
// that reads as viewed from underneath, new pieces at the bottom of frame
// impossible to identify), not from the math alone. Viewer3D.tsx's own
// frameObject uses a (+x, -y, +z) offset, and after this scene's own
// `group.rotation.x = Math.PI` flip (LDraw -Y-up -> world +Y-up, see
// loadStepped's own comment), a NEGATIVE Y offset puts the camera BELOW
// the model looking up at its underside -- Viewer3D gets away with this
// because OrbitControls lets a user immediately drag to a better angle;
// this headless renderer has no such rescue, since the very first frame
// captured IS the final image. +Y here, not Viewer3D's -Y, is the fix.
const VIEW_DIRECTION = new THREE.Vector3(1, 1, 1).normalize();

/** Points the camera at `box`'s center from the same fixed direction every
 * time (an isometric-ish corner view, the same relative offset
 * Viewer3D.tsx's own frameObject uses, so the PDF's angle matches the
 * interactive preview elsewhere in the product), at whatever distance
 * exactly fits `box`'s bounding sphere in the vertical FOV plus a small
 * margin. This is what makes per-step framing possible: called with a
 * different box (however much of the model is visible at that step)
 * every time, rather than once with the whole model's box.
 *
 * A real bug lived here until caught by inspecting actual rendered
 * output, not just the math in isolation: using a raw (dist, -dist, dist)
 * offset (as Viewer3D.tsx's own frameObject does) makes the true
 * Euclidean camera-to-target distance dist*sqrt(3), not dist -- Viewer3D
 * absorbs that silently into its own hand-tuned "maxDim * 1.8" margin
 * constant (and the user can always zoom further with OrbitControls
 * regardless), but this headless renderer has no such safety net: the
 * initial framing IS the final image. The r/sin(fov/2) distance formula
 * below is only correct if applied along the ACTUAL distance to target,
 * so the offset must be a normalized direction scaled by `dist`, not
 * three raw dist-sized components. */
function frameBox(box) {
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, MIN_FRAME_RADIUS_LDU);
  const dist = (radius / Math.sin(FOV_RAD / 2)) * FRAME_MARGIN;

  camera.position.copy(center).addScaledVector(VIEW_DIRECTION, dist);
  camera.lookAt(center);
  camera.near = Math.max(dist / 100, 0.1);
  camera.far = dist * 100;
  camera.updateProjectionMatrix();

  window.__bf.lastFrame = { size: size.toArray(), center: center.toArray(), radius, dist };
}

/** A solid, semi-transparent box plus a bright wireframe outline around
 * it -- replaces a plain Box3Helper (just a thin wireframe line), which
 * turned out to be nearly invisible against similarly-light-colored
 * parts once compressed into a PDF-sized screenshot, a real legibility
 * complaint from production use, not a hypothetical. The solid fill is
 * what actually draws the eye; the wireframe sharpens its edges on top. */
function buildHighlight(box) {
  const size = new THREE.Vector3();
  box.getSize(size);
  const center = new THREE.Vector3();
  box.getCenter(center);

  const geometry = new THREE.BoxGeometry(size.x || 1, size.y || 1, size.z || 1);
  const fillMaterial = new THREE.MeshBasicMaterial({
    color: HIGHLIGHT_COLOR,
    transparent: true,
    opacity: 0.28,
    depthWrite: false,
  });
  const fill = new THREE.Mesh(geometry, fillMaterial);

  const edgesGeometry = new THREE.EdgesGeometry(geometry);
  const edgeMaterial = new THREE.LineBasicMaterial({ color: HIGHLIGHT_COLOR });
  const edges = new THREE.LineSegments(edgesGeometry, edgeMaterial);

  const group = new THREE.Group();
  group.add(fill, edges);
  group.position.copy(center);
  return group;
}

function clearHighlight() {
  if (!highlightGroup) return;
  highlightGroup.traverse((c) => {
    if (c.geometry) c.geometry.dispose();
    if (c.material) c.material.dispose();
  });
  scene.remove(highlightGroup);
  highlightGroup = null;
}
