import type { Area } from "react-easy-crop";

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => resolve(image));
    image.addEventListener("error", reject);
    image.src = src;
  });
}

/** Renders the user-selected crop rectangle (in source-image pixels) onto a
 * same-size canvas and exports it — the icon everywhere in the app (list
 * thumbnail, graph node, detail panel portrait) is this single cropped file,
 * not the original upload, so every view of it stays consistent. */
export async function cropImageToBlob(imageSrc: string, cropPixels: Area): Promise<Blob> {
  const image = await loadImage(imageSrc);
  const canvas = document.createElement("canvas");
  canvas.width = cropPixels.width;
  canvas.height = cropPixels.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");

  ctx.drawImage(
    image,
    cropPixels.x,
    cropPixels.y,
    cropPixels.width,
    cropPixels.height,
    0,
    0,
    cropPixels.width,
    cropPixels.height,
  );

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas toBlob failed"))),
      "image/jpeg",
      0.92,
    );
  });
}

/** A very wide or tall source, laid out at native scale, would need a
 * multi-thousand-pixel canvas to stay uncropped — capped here so "Fit"
 * never produces an unreasonably large export. */
const FIT_MAX_LONG_EDGE = 1024;

export interface FitLayout {
  canvasWidth: number;
  canvasHeight: number;
  drawWidth: number;
  drawHeight: number;
  dx: number;
  dy: number;
}

/** Where a source image lands inside the smallest `aspect`-ratio box that
 * contains it without cropping. The box hugs the source at native scale
 * (crisp, no upscaling) unless that would exceed FIT_MAX_LONG_EDGE, in which
 * case both the box and the image shrink together — the image still fills
 * one full edge of the box either way, so it's never letterboxed on both
 * axes at once. Pure geometry: no DOM, so it's cheap to unit test directly. */
export function computeFitLayout(
  sourceWidth: number,
  sourceHeight: number,
  aspect: number,
  maxLongEdge: number = FIT_MAX_LONG_EDGE,
): FitLayout {
  const wideEnoughForAspect = sourceWidth / sourceHeight >= aspect;
  const boxWidth = wideEnoughForAspect ? sourceWidth : sourceHeight * aspect;
  const boxHeight = wideEnoughForAspect ? sourceWidth / aspect : sourceHeight;

  const longEdge = Math.max(boxWidth, boxHeight);
  const scale = longEdge > maxLongEdge ? maxLongEdge / longEdge : 1;

  const canvasWidth = Math.round(boxWidth * scale);
  const canvasHeight = Math.round(boxHeight * scale);
  const drawWidth = Math.round(sourceWidth * scale);
  const drawHeight = Math.round(sourceHeight * scale);

  return {
    canvasWidth,
    canvasHeight,
    drawWidth,
    drawHeight,
    dx: Math.round((canvasWidth - drawWidth) / 2),
    dy: Math.round((canvasHeight - drawHeight) / 2),
  };
}

export interface CoverLayout {
  drawWidth: number;
  drawHeight: number;
  dx: number;
  dy: number;
}

/** Where a source image lands when scaled to fully cover a target box
 * (the `object-fit: cover` algorithm): scaled up just enough that both
 * edges meet or exceed the box, then centered — whichever axis doesn't
 * land exactly overhangs symmetrically. `overscan` inflates that scale a
 * little further, for callers that go on to blur the result and want the
 * (now-transparent-edged) overhang to clear the visible frame instead of
 * bleeding a soft edge in from the box's own boundary. Pure geometry, same
 * rationale as computeFitLayout: no DOM, cheap to unit test directly. */
export function computeCoverLayout(
  sourceWidth: number,
  sourceHeight: number,
  targetWidth: number,
  targetHeight: number,
  overscan: number = 1,
): CoverLayout {
  const scale = Math.max(targetWidth / sourceWidth, targetHeight / sourceHeight) * overscan;
  const drawWidth = Math.round(sourceWidth * scale);
  const drawHeight = Math.round(sourceHeight * scale);
  return {
    drawWidth,
    drawHeight,
    dx: Math.round((targetWidth - drawWidth) / 2),
    dy: Math.round((targetHeight - drawHeight) / 2),
  };
}

// Beyond the minimum needed to cover the frame, so the blur's soft
// (partly-transparent) edge sits outside the visible canvas on every side
// rather than right at the frame boundary — see computeCoverLayout.
const BACKGROUND_COVER_OVERSCAN = 1.15;
// Fraction of the frame's shorter edge, so the background reads as
// consistently "blurred" whether the export is a tiny test fixture or a
// full-size photo capped by FIT_MAX_LONG_EDGE.
const BACKGROUND_BLUR_FRACTION = 0.08;
const BACKGROUND_BLUR_MIN_PX = 4;

/** The "Fit" counterpart to cropImageToBlob: the whole source is kept, laid
 * out by computeFitLayout and never cropped — for logos and icons where
 * losing any of the source isn't acceptable. The padding needed to reach
 * `aspect` is filled with a blurred, cover-scaled copy of the same image
 * instead of a flat matte, so it reads as part of the photo (and never as a
 * stray white/transparent bar) in both light and dark themes. */
export async function fitImageToBlob(imageSrc: string, aspect: number): Promise<Blob> {
  const image = await loadImage(imageSrc);
  const layout = computeFitLayout(image.naturalWidth, image.naturalHeight, aspect);
  const canvas = document.createElement("canvas");
  canvas.width = layout.canvasWidth;
  canvas.height = layout.canvasHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");

  const cover = computeCoverLayout(
    image.naturalWidth,
    image.naturalHeight,
    layout.canvasWidth,
    layout.canvasHeight,
    BACKGROUND_COVER_OVERSCAN,
  );
  const blurPx = Math.max(
    Math.round(Math.min(layout.canvasWidth, layout.canvasHeight) * BACKGROUND_BLUR_FRACTION),
    BACKGROUND_BLUR_MIN_PX,
  );
  ctx.filter = `blur(${blurPx}px)`;
  ctx.drawImage(image, cover.dx, cover.dy, cover.drawWidth, cover.drawHeight);
  ctx.filter = "none";

  // The real, uncropped source on top of its own blurred backdrop — never
  // scaled beyond computeFitLayout's own (rare, cap-driven) downscale.
  ctx.drawImage(image, layout.dx, layout.dy, layout.drawWidth, layout.drawHeight);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas toBlob failed"))),
      "image/jpeg",
      0.92,
    );
  });
}
