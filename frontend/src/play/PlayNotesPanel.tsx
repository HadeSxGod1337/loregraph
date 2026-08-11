import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ProseMirrorDoc } from "../api/types";
import { RichTextField } from "../components/entity/RichTextField";
import { RichTextView } from "../components/entity/RichTextView";
import { Icon } from "../components/ui/Icon";
import {
  usePlayCreateNote,
  usePlayDeleteNote,
  usePlayNotes,
} from "../hooks/usePlay";

const EMPTY_DOC: ProseMirrorDoc = { type: "doc", content: [{ type: "paragraph" }] };

function isBlank(doc: ProseMirrorDoc): boolean {
  return JSON.stringify(doc) === JSON.stringify(EMPTY_DOC);
}

/** A player's notes on one entity: their own (private or public) plus other
 * players' public ones. The DM sees all of these too (from the DM side). */
export function PlayNotesPanel({ entityId }: { entityId: string }) {
  const { t } = useTranslation();
  const { data: notes } = usePlayNotes(entityId, true);
  const createNote = usePlayCreateNote(entityId);
  const deleteNote = usePlayDeleteNote(entityId);

  const [draft, setDraft] = useState<ProseMirrorDoc>(EMPTY_DOC);
  const [isPublic, setIsPublic] = useState(false);

  function handleAdd() {
    if (isBlank(draft)) return;
    createNote.mutate(
      { body: draft, is_public: isPublic },
      {
        onSuccess: () => {
          setDraft(EMPTY_DOC);
          setIsPublic(false);
        },
      },
    );
  }

  return (
    <section className="play-notes">
      <h2>{t("play.notesTitle")}</h2>

      <div className="play-note-form">
        {/* entityId undefined: notes have no attachments of their own. */}
        <RichTextField value={draft} onChange={setDraft} entityId={undefined} />
        <div className="play-note-form-actions">
          <label className="play-note-public">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            {t("play.notePublic")}
          </label>
          <button
            type="button"
            className="button-primary button-sm"
            onClick={handleAdd}
            disabled={createNote.isPending || isBlank(draft)}
          >
            {t("play.addNote")}
          </button>
        </div>
      </div>

      {notes && notes.length > 0 ? (
        <ul className="play-note-list">
          {notes.map((note) => (
            <li key={note.id} className={note.is_own ? "own" : ""}>
              <div className="play-note-meta">
                <span className="play-note-author">
                  {note.is_own ? t("play.you") : note.author_name}
                </span>
                <span
                  className={
                    "note-visibility " + (note.is_public ? "is-public" : "is-private")
                  }
                >
                  {note.is_public ? t("play.public") : t("play.private")}
                </span>
                {note.is_own && (
                  <button
                    type="button"
                    className="icon-button icon-button-danger"
                    onClick={() => deleteNote.mutate(note.id)}
                    title={t("common.delete")}
                  >
                    <Icon name="trash" size={13} />
                  </button>
                )}
              </div>
              <RichTextView value={note.body} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="play-empty">{t("play.noNotes")}</p>
      )}
    </section>
  );
}
