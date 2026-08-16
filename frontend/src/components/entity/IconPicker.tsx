import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import { API_URL } from "../../api/client";
import type { AttachmentRef } from "../../api/types";
import { useClearEntityIcon, useSetEntityIcon } from "../../hooks/useEntity";
import { useUploadAttachment } from "../../hooks/useAttachments";
import { useObjectUrl } from "../../hooks/useObjectUrl";
import { ImageCropModal } from "./ImageCropModal";

interface IconPickerProps {
  projectId: string;
  entityId: string | undefined;
  icon: AttachmentRef | null;
  /** Pre-save staging: while the entity doesn't exist yet (entityId is
   * undefined), a cropped icon has nowhere to upload to — the attachment
   * store keys everything off an entity row. Instead the picked file is held
   * here, controlled by the caller, which uploads it and sets it as the icon
   * itself right after the entity is created (see EntityEditPage). */
  stagedIcon?: File | null;
  onStagedIconChange?: (file: File | null) => void;
}

export function IconPicker({
  projectId,
  entityId,
  icon,
  stagedIcon = null,
  onStagedIconChange,
}: IconPickerProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadAttachment(entityId ?? "");
  const setIcon = useSetEntityIcon(projectId, entityId ?? "");
  const clearIcon = useClearEntityIcon(projectId, entityId ?? "");
  const staging = entityId === undefined;
  // Object URL for whatever file was just picked, held only long enough to
  // crop it — revoked as soon as the crop dialog closes either way.
  const [pendingImageSrc, setPendingImageSrc] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    };
  }, [pendingImageSrc]);

  const stagedPreviewUrl = useObjectUrl(stagedIcon);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPendingImageSrc(URL.createObjectURL(file));
  }

  async function handleCropped(blob: Blob) {
    if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    setPendingImageSrc(null);
    const croppedFile = new File([blob], "icon.jpg", { type: "image/jpeg" });
    if (staging) {
      onStagedIconChange?.(croppedFile);
      return;
    }
    const attachment = await upload.mutateAsync(croppedFile);
    setIcon.mutate(attachment.id);
  }

  function handleCropCancel() {
    if (pendingImageSrc) URL.revokeObjectURL(pendingImageSrc);
    setPendingImageSrc(null);
  }

  const hasIcon = staging ? stagedIcon !== null : icon !== null;

  return (
    <div className="icon-picker">
      <div className="icon-picker-preview">
        {staging && stagedPreviewUrl ? (
          <img src={stagedPreviewUrl} alt="" />
        ) : !staging && icon ? (
          <img src={API_URL + icon.url} alt="" />
        ) : (
          <span>{t("icon.noIcon")}</span>
        )}
      </div>
      <div className="icon-picker-actions">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={upload.isPending || setIcon.isPending}
        >
          {hasIcon ? t("common.replace") : t("common.upload")}
        </button>
        {hasIcon && (
          <button
            type="button"
            className="button-danger"
            onClick={() =>
              staging ? onStagedIconChange?.(null) : clearIcon.mutate()
            }
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
