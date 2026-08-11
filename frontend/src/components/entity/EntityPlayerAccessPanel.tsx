import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Entity, ProseMirrorDoc } from "../../api/types";
import { useEntityPlayerNotes, useSetEntityPlayerView } from "../../hooks/useEntity";
import { Icon } from "../ui/Icon";
import { RichTextField } from "./RichTextField";
import { RichTextView } from "./RichTextView";

const EMPTY_DOC: ProseMirrorDoc = { type: "doc", content: [{ type: "paragraph" }] };

function isBlankDoc(doc: ProseMirrorDoc | null): boolean {
  return doc === null || JSON.stringify(doc) === JSON.stringify(EMPTY_DOC);
}

/** DM controls for limited player access, in one place used by both the entity
 * editor and the graph detail panel. Works with or without a sheet template —
 * the field whitelist is its own list of keys, so the sheet renderer and the
 * template designer are never touched. */
export function EntityPlayerAccessPanel({
  projectId,
  entity,
}: {
  projectId: string;
  entity: Entity;
}) {
  const { t } = useTranslation();
  const setPlayerView = useSetEntityPlayerView(projectId, entity.id);
  const notes = useEntityPlayerNotes(projectId, entity.id);

  const [revealed, setRevealed] = useState(entity.revealed_to_players);
  const [playerText, setPlayerText] = useState<ProseMirrorDoc>(
    entity.player_text ?? EMPTY_DOC,
  );
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(
    () =>
      new Set(entity.fields.filter((f) => f.visible_to_players).map((f) => f.key)),
  );

  // Follow a server refresh (e.g. after saving elsewhere) so the panel doesn't
  // keep showing stale toggles.
  useEffect(() => {
    setRevealed(entity.revealed_to_players);
    setPlayerText(entity.player_text ?? EMPTY_DOC);
    setVisibleKeys(
      new Set(entity.fields.filter((f) => f.visible_to_players).map((f) => f.key)),
    );
  }, [entity]);

  function toggleKey(key: string) {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleSave() {
    setPlayerView.mutate({
      revealed_to_players: revealed,
      player_text: isBlankDoc(playerText) ? null : playerText,
      visible_field_keys: [...visibleKeys],
    });
  }

  const fieldKeys = entity.fields.map((f) => f.key).filter(Boolean);

  return (
    <details className="player-access-panel">
      <summary>
        <Icon name={revealed ? "eye" : "eye-off"} size={14} />
        {t("playerAccess.title")}
        {revealed && <span className="player-access-badge">{t("playerAccess.on")}</span>}
      </summary>

      <label className="player-access-toggle">
        <input
          type="checkbox"
          checked={revealed}
          onChange={(e) => setRevealed(e.target.checked)}
        />
        {t("playerAccess.revealed")}
      </label>

      <div className="player-access-section">
        <span className="player-access-label">{t("playerAccess.playerText")}</span>
        <RichTextField
          value={playerText}
          onChange={setPlayerText}
          entityId={entity.id}
        />
      </div>

      {fieldKeys.length > 0 && (
        <div className="player-access-section">
          <span className="player-access-label">{t("playerAccess.visibleFields")}</span>
          <ul className="player-access-fields">
            {fieldKeys.map((key) => (
              <li key={key}>
                <label>
                  <input
                    type="checkbox"
                    checked={visibleKeys.has(key)}
                    onChange={() => toggleKey(key)}
                  />
                  {key}
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="player-access-section">
        <span className="player-access-label">
          {t("playerAccess.playerNotes")}
        </span>
        {notes.data && notes.data.length > 0 ? (
          <ul className="player-access-notes">
            {notes.data.map((note) => (
              <li key={note.id}>
                <span className="note-meta">
                  {note.author_name}
                  <span
                    className={
                      "note-visibility " + (note.is_public ? "is-public" : "is-private")
                    }
                  >
                    {note.is_public
                      ? t("playerAccess.public")
                      : t("playerAccess.private")}
                  </span>
                </span>
                <RichTextView value={note.body} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="player-access-empty">{t("playerAccess.noNotes")}</p>
        )}
      </div>

      <button
        type="button"
        className="button-primary button-sm"
        onClick={handleSave}
        disabled={setPlayerView.isPending}
      >
        {t("playerAccess.save")}
      </button>
    </details>
  );
}
