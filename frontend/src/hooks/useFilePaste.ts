import { useCallback, useEffect } from "react";

/** Clipboard images (a screenshot, "copy image" from a browser) arrive with
 * a useless or missing name — "image.png" for every screenshot, so several
 * pasted in one turn would be indistinguishable in the attachment chips and
 * on the backend. Renamed on the way in, keeping the extension the MIME type
 * implies. */
function nameClipboardFile(file: File, index: number): File {
  if (file.name && file.name !== "image.png") return file;
  const extension = file.type.split("/")[1] || "png";
  // Attachments live only inside one chat turn, so a wall-clock time is
  // unique enough and stays short in the chip.
  const stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, "-");
  return new File([file], `pasted-${stamp}-${index + 1}.${extension}`, {
    type: file.type,
  });
}

/** Files carried by a paste, ignoring the text/html and text/plain flavors a
 * copied image also brings along. */
function filesFromClipboard(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files: File[] = [];
  for (const item of Array.from(data.items)) {
    if (item.kind !== "file") continue;
    const file = item.getAsFile();
    if (file) files.push(nameClipboardFile(file, files.length));
  }
  return files;
}

/** True when the paste is destined for some other text field — a paste there
 * belongs to that field, not to us. */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement
  );
}

/**
 * Attaching files pasted from the clipboard, as a companion to drag-and-drop
 * (see useFileDrop).
 *
 * Two entry points, because a screenshot is usually taken with the chat field
 * *not* focused: `pasteHandlers` for the chat input itself, and a
 * document-level listener that only fires when no other text field would have
 * consumed the paste anyway.
 */
export function useFilePaste(onFiles: (files: File[]) => void, enabled = true) {
  const onPaste = useCallback(
    (e: React.ClipboardEvent) => {
      if (!enabled) return;
      const pasted = filesFromClipboard(e.clipboardData);
      if (pasted.length === 0) return;
      // Only claim the event once files are actually taken, so pasting text
      // into the textarea keeps working normally.
      e.preventDefault();
      onFiles(pasted);
    },
    [enabled, onFiles],
  );

  useEffect(() => {
    if (!enabled) return;
    function handleDocumentPaste(e: ClipboardEvent) {
      if (isEditableTarget(e.target)) return;
      const pasted = filesFromClipboard(e.clipboardData);
      if (pasted.length === 0) return;
      e.preventDefault();
      onFiles(pasted);
    }
    document.addEventListener("paste", handleDocumentPaste);
    return () => document.removeEventListener("paste", handleDocumentPaste);
  }, [enabled, onFiles]);

  return { pasteHandlers: { onPaste } };
}
