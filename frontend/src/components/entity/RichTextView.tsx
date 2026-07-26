import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import { useEffect, useMemo } from "react";
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

  // `content` above is only the editor's *initial* document. Without this the
  // view keeps whatever it was first mounted with — a sheet that reuses one
  // view for two tabs, or a field the server refreshed, silently showed stale
  // (or blank) text. emitUpdate:false — nothing is editing here.
  useEffect(() => {
    if (!editor) return;
    if (JSON.stringify(editor.getJSON()) === JSON.stringify(value)) return;
    editor.commands.setContent(value as JSONContent, { emitUpdate: false });
  }, [editor, value]);

  if (!editor) return null;
  return <EditorContent editor={editor} className="rich-text-content rich-text-view" />;
}
