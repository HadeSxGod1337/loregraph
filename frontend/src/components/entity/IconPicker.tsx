import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import { API_URL } from "../../api/client";
import type { AttachmentRef } from "../../api/types";
import { useClearEntityIcon, useSetEntityIcon } from "../../hooks/useEntity";
import { useUploadAttachment } from "../../hooks/useAttachments";
import { ImageCropModal } from "./ImageCropModal";

interface IconPickerProps {
  projectId: string;
  entityId: string | undefined;
  icon: AttachmentRef | null;
}

export function IconPicker({ projectId, entityId, icon }: IconPickerProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadAttachment(entityId ?? "");
  const setIcon = useSetEntityIcon(projectId, entityId ?? "");
  const clearIcon = useClearEntityIcon(projectId, entityId ?? "");
  // Object URL for whatever file was just picked, held only long enough to
  // crop it — revoked as soon as the crop dialog closes either way.
  const [pendingImageSrc, setPendingImageSrc] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    };
  }, [pendingImageSrc]);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !entityId) return;
    setPendingImageSrc(URL.createObjectURL(file));
  }

  async function handleCropped(blob: Blob) {
    if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    setPendingImageSrc(null);
    const croppedFile = new File([blob], "icon.jpg", { type: "image/jpeg" });
    const attachment = await upload.mutateAsync(croppedFile);
    setIcon.mutate(attachment.id);
  }

  function handleCropCancel() {
    if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    setPendingImageSrc(null);
  }

  if (!entityId) {
    return <p className="icon-picker-placeholder">{t("icon.saveFirst")}</p>;
  }

  return (
    <div className="icon-picker">
      <div className="icon-picker-preview">
        {icon ? <img src={API_URL + icon.url} alt="" /> : <span>{t("icon.noIcon")}</span>}
      </div>
      <div className="icon-picker-actions">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={upload.isPending || setIcon.isPending}
        >
          {icon ? t("common.replace") : t("common.upload")}
        </button>
        {icon && (
          <button
            type="button"
            className="button-danger"
            onClick={() => clearIcon.mutate()}
            disabled={clearIcon.isPending}
          >
            {t("common.remove")}
          </button>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={handleFileChange}
      />
      {pendingImageSrc && (
        <ImageCropModal
          imageSrc={pendingImageSrc}
          onCropped={(blob) => void handleCropped(blob)}
          onCancel={handleCropCancel}
        />
      )}
    </div>
  );
}
