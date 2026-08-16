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

/** The "Fit" counterpart to cropImageToBlob: the whole source is kept, laid
 * out by computeFitLayout and padded to `aspect` with a flat background
 * instead of cropped — for logos and icons where losing any of the source
 * isn't acceptable. */
export async function fitImageToBlob(
  imageSrc: string,
  aspect: number,
  background: string,
): Promise<Blob> {
  const image = await loadImage(imageSrc);
  const layout = computeFitLayout(image.naturalWidth, image.naturalHeight, aspect);
  const canvas = document.createElement("canvas");
  canvas.width = layout.canvasWidth;
  canvas.height = layout.canvasHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");

  ctx.fillStyle = background;
  ctx.fillRect(0, 0, layout.canvasWidth, layout.canvasHeight);
  ctx.drawImage(image, layout.dx, layout.dy, layout.drawWidth, layout.drawHeight);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas toBlob failed"))),
      "image/jpeg",
      0.92,
    );
  });
}
