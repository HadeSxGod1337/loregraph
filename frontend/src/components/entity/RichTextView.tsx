import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import { useMemo } from "react";
import { useMatch } from "react-router-dom";

import type { ProseMirrorDoc } from "../../api/types";
import { buildRichTextExtensions } from "./entityLink";

/** Read-only render of a rich_text field's actual formatting (bold, lists,
 * inline images, entity links, ...) — used anywhere we show a field's value
 * without editing it, so the view doesn't silently drop styling like a
 * plain-text summary would. */
export function RichTextView({ value }: { value: ProseMirrorDoc }) {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const extensions = useMemo(() => buildRichTextExtensions(projectId), [projectId]);

  const editor = useEditor({
    extensions,
    content: value as JSONContent,
    editable: false,
  });

  if (!editor) return null;
  return <EditorContent editor={editor} className="rich-text-content rich-text-view" />;
}
