import { useCallback, useState } from "react";
import Cropper, { type Area, type Point } from "react-easy-crop";
import { useTranslation } from "react-i18next";

import { cropImageToBlob, fitImageToBlob } from "./cropImage";

interface ImageCropModalProps {
  imageSrc: string;
  onCropped: (blob: Blob) => void;
  onCancel: () => void;
}

// Wide banner, matching the detail panel's .portrait box (width:100%,
// max-height:160px — roughly this ratio at the panel's own width). The
// small square contexts (list avatar, graph node) don't get their own crop
// step — they just `object-fit: cover` the center of this same file, which
// is why the crop is wide rather than square: composing "what's in the
// middle" here is what ends up in those square views too.
const ICON_CROP_ASPECT = 2;

type CropMode = "fill" | "fit";

/** One crop, applied once at upload time — the resulting file is what's
 * stored and shown everywhere (list thumbnail, graph node, detail panel
 * portrait). Fill crops the source to the frame like before; Fit keeps the
 * whole source and pads instead, for logos and icons that shouldn't lose any
 * of their edges. */
export function ImageCropModal({ imageSrc, onCropped, onCancel }: ImageCropModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<CropMode>("fill");
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const [saving, setSaving] = useState(false);

  const handleCropComplete = useCallback((_area: Area, areaPixels: Area) => {
    setCroppedAreaPixels(areaPixels);
  }, []);

  async function handleSave() {
    if (mode === "fill" && !croppedAreaPixels) return;
    setSaving(true);
    try {
      const blob =
        mode === "fill"
          ? await cropImageToBlob(imageSrc, croppedAreaPixels!)
          : await fitImageToBlob(imageSrc, ICON_CROP_ASPECT);
      onCropped(blob);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="dialog image-crop-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("icon.cropTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{t("icon.cropTitle")}</h2>

        <div
          className="segmented image-crop-mode"
          role="group"
          aria-label={t("icon.cropModeLabel")}
        >
          <button
            type="button"
            className={mode === "fill" ? "active" : undefined}
            aria-pressed={mode === "fill"}
            onClick={() => setMode("fill")}
          >
            {t("icon.cropModeFill")}
          </button>
          <button
            type="button"
            className={mode === "fit" ? "active" : undefined}
            aria-pressed={mode === "fit"}
            onClick={() => setMode("fit")}
          >
            {t("icon.cropModeFit")}
          </button>
        </div>
        <p className="field-hint">
          {mode === "fill" ? t("icon.cropModeFillHint") : t("icon.cropModeFitHint")}
        </p>

        {mode === "fill" ? (
          <>
            <div className="image-crop-area">
              <Cropper
                image={imageSrc}
                crop={crop}
                zoom={zoom}
                aspect={ICON_CROP_ASPECT}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={handleCropComplete}
              />
            </div>
            <label className="image-crop-zoom">
              {t("icon.cropZoom")}
              <input
                type="range"
                min={1}
                max={3}
                step={0.01}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
              />
            </label>
          </>
        ) : (
          // Mirrors fitImageToBlob's canvas: a blurred, cover-scaled copy of
          // the same image behind an object-fit: contain copy on top — CSS
          // approximation of the same two-layer composite the export bakes
          // into the file, so this preview reads the same as the result.
          <div className="image-crop-fit-preview">
            <img className="image-crop-fit-preview-bg" src={imageSrc} alt="" aria-hidden="true" />
            <img className="image-crop-fit-preview-fg" src={imageSrc} alt="" />
          </div>
        )}

        <div className="dialog-actions">
          <button type="button" className="button-ghost" onClick={onCancel} disabled={saving}>
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="button-primary"
            onClick={() => void handleSave()}
            disabled={saving || (mode === "fill" && !croppedAreaPixels)}
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
