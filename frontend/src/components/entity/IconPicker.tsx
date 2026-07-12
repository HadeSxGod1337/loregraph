import { useRef, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import { API_URL } from "../../api/client";
import type { AttachmentRef } from "../../api/types";
import { useClearEntityIcon, useSetEntityIcon } from "../../hooks/useEntity";
import { useUploadAttachment } from "../../hooks/useAttachments";

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

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !entityId) return;
    const attachment = await upload.mutateAsync(file);
    setIcon.mutate(attachment.id);
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
        onChange={(e) => void handleFileChange(e)}
      />
    </div>
  );
}
