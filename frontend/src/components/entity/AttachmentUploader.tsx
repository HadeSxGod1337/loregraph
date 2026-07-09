import type { ChangeEvent } from "react";

import { API_URL } from "../../api/client";
import {
  useAttachments,
  useDeleteAttachment,
  useUploadAttachment,
} from "../../hooks/useAttachments";

export function AttachmentUploader({ entityId }: { entityId: string }) {
  const { data: attachments } = useAttachments(entityId);
  const upload = useUploadAttachment(entityId);
  const remove = useDeleteAttachment(entityId);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      upload.mutate(file);
      e.target.value = "";
    }
  }

  return (
    <div className="attachment-uploader">
      <h3>Attachments</h3>
      <input type="file" accept="image/*" onChange={handleFileChange} />
      {upload.isPending && <p>Uploading...</p>}

      <div className="attachment-gallery">
        {attachments?.map((attachment) => (
          <div key={attachment.id} className="attachment-thumb">
            <img src={API_URL + attachment.url} alt={attachment.original_filename} />
            <button
              type="button"
              className="button-danger"
              onClick={() => remove.mutate(attachment.id)}
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
