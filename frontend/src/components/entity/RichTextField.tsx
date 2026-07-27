import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import { useEffect, useMemo, useRef, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { useMatch } from "react-router-dom";

import { API_URL } from "../../api/client";
import type { ProseMirrorDoc } from "../../api/types";
import { useUploadAttachment } from "../../hooks/useAttachments";
import { RichTextToolbar } from "./RichTextToolbar";
import { buildRichTextExtensions } from "./entityLink";

interface RichTextFieldProps {
  value: ProseMirrorDoc;
  onChange: (doc: ProseMirrorDoc) => void;
  entityId: string | undefined;
}

export function RichTextField({ value, onChange, entityId }: RichTextFieldProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadAttachment(entityId ?? "");
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const extensions = useMemo(() => buildRichTextExtensions(projectId), [projectId]);

  const editor = useEditor({
    extensions,
    content: value as JSONContent,
    onUpdate: ({ editor }) => onChange(editor.getJSON() as ProseMirrorDoc),
  });

  // `content` is the editor's initial document only. While typing this is a
  // no-op (the parent stores exactly what onUpdate handed it), but when the
  // same editor is handed a different field's document — a sheet reusing one
  // instance across tabs, or a server refresh — it must follow, or it keeps
  // showing (and then saving) the previous field's text.
  useEffect(() => {
    if (!editor) return;
    if (JSON.stringify(editor.getJSON()) === JSON.stringify(value)) return;
    editor.commands.setContent(value as JSONContent, { emitUpdate: false });
  }, [editor, value]);

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !editor || !entityId) return;
    const attachment = await upload.mutateAsync(file);
    editor.chain().focus().setImage({ src: API_URL + attachment.url }).run();
  }

  if (!editor) return null;

  return (
    <div className="rich-text-field">
      <RichTextToolbar
        editor={editor}
        onInsertImage={() => fileInputRef.current?.click()}
        imageDisabled={!entityId || upload.isPending}
        imageTitle={entityId ? t("richText.insertImage") : t("richText.saveFirstForImage")}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => void handleFileChange(e)}
      />
      <EditorContent editor={editor} className="rich-text-content" />
    </div>
  );
}
