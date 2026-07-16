import { useCallback, useState } from "react";
import Cropper, { type Area, type Point } from "react-easy-crop";
import { useTranslation } from "react-i18next";

import { cropImageToBlob } from "./cropImage";

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

/** One crop, applied once at upload time — the resulting file is what's
 * stored and shown everywhere (list thumbnail, graph node, detail panel
 * portrait). */
export function ImageCropModal({ imageSrc, onCropped, onCancel }: ImageCropModalProps) {
  const { t } = useTranslation();
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const [saving, setSaving] = useState(false);

  const handleCropComplete = useCallback((_area: Area, areaPixels: Area) => {
    setCroppedAreaPixels(areaPixels);
  }, []);

  async function handleSave() {
    if (!croppedAreaPixels) return;
    setSaving(true);
    try {
      const blob = await cropImageToBlob(imageSrc, croppedAreaPixels);
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
        <div className="dialog-actions">
          <button type="button" className="button-ghost" onClick={onCancel} disabled={saving}>
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="button-primary"
            onClick={() => void handleSave()}
            disabled={saving || !croppedAreaPixels}
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
