import Image from "@tiptap/extension-image";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

import type { ProseMirrorDoc } from "../../api/types";

/** Read-only render of a rich_text field's actual formatting (bold, lists,
 * inline images, ...) — used anywhere we show a field's value without
 * editing it, so the view doesn't silently drop styling like a plain-text
 * summary would. */
export function RichTextView({ value }: { value: ProseMirrorDoc }) {
  const editor = useEditor({
    extensions: [StarterKit, Image, Underline],
    content: value as JSONContent,
    editable: false,
  });

  if (!editor) return null;
  return <EditorContent editor={editor} className="rich-text-content rich-text-view" />;
}
