import Image from "@tiptap/extension-image";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useRef, type ChangeEvent } from "react";

import { API_URL } from "../../api/client";
import type { ProseMirrorDoc } from "../../api/types";
import { useUploadAttachment } from "../../hooks/useAttachments";

interface RichTextFieldProps {
  value: ProseMirrorDoc;
  onChange: (doc: ProseMirrorDoc) => void;
  entityId: string | undefined;
}

interface ToolbarButtonProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

function ToolbarButton({ label, isActive, onClick }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={isActive ? "rich-text-toolbar-btn active" : "rich-text-toolbar-btn"}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

export function RichTextField({ value, onChange, entityId }: RichTextFieldProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadAttachment(entityId ?? "");

  const editor = useEditor({
    extensions: [StarterKit, Image, Underline],
    content: value as JSONContent,
    onUpdate: ({ editor }) => onChange(editor.getJSON() as ProseMirrorDoc),
  });

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
      <div className="rich-text-toolbar">
        <ToolbarButton
          label="B"
          isActive={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolbarButton
          label="I"
          isActive={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolbarButton
          label="U"
          isActive={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
        />
        <ToolbarButton
          label="S"
          isActive={editor.isActive("strike")}
          onClick={() => editor.chain().focus().toggleStrike().run()}
        />
        <span className="rich-text-toolbar-divider" />
        <ToolbarButton
          label="• List"
          isActive={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        />
        <ToolbarButton
          label="1. List"
          isActive={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        />
        <span className="rich-text-toolbar-divider" />
        <button
          type="button"
          className="rich-text-toolbar-btn"
          disabled={!entityId || upload.isPending}
          onClick={() => fileInputRef.current?.click()}
          title={entityId ? "Insert image" : "Save the entity first to insert images"}
        >
          Image
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => void handleFileChange(e)}
        />
      </div>
      <EditorContent editor={editor} className="rich-text-content" />
    </div>
  );
}
