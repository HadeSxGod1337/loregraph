import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Player, PlayerCreated } from "../../api/types";
import {
  useCreatePlayer,
  useDeletePlayer,
  useNetworkStatus,
  usePlayers,
  useRevokePlayer,
  useRotatePlayer,
} from "../../hooks/usePlayers";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Icon } from "../ui/Icon";
import { NetworkStatusNotice } from "./NetworkStatusNotice";

/** DM management of player invites. Full links are shown once, at create or
 * rotate time — the raw token is never stored, so a lost link is rotated, not
 * recovered. */
export function PlayersPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { data: players } = usePlayers(projectId);
  const { data: network } = useNetworkStatus();
  const createPlayer = useCreatePlayer(projectId);
  const rotatePlayer = useRotatePlayer(projectId);
  const revokePlayer = useRevokePlayer(projectId);
  const deletePlayer = useDeletePlayer(projectId);

  const [inviting, setInviting] = useState(false);
  const [newName, setNewName] = useState("");
  const [freshLink, setFreshLink] = useState<PlayerCreated | null>(null);
  const [deleting, setDeleting] = useState<Player | null>(null);

  function handleInvite() {
    if (!newName.trim()) return;
    createPlayer.mutate(newName.trim(), {
      onSuccess: (created) => {
        setFreshLink(created);
        setNewName("");
        setInviting(false);
      },
    });
  }

  function handleRotate(player: Player) {
    rotatePlayer.mutate(player.id, {
      onSuccess: (created) => setFreshLink(created),
    });
  }

  return (
    <section className="settings-card">
      <p className="field-hint">{t("players.intro")}</p>
      {network && <NetworkStatusNotice status={network} />}

      {!inviting ? (
        <button type="button" onClick={() => setInviting(true)}>
          <Icon name="plus" size={14} />
          {t("players.invite")}
        </button>
      ) : (
        <div className="player-invite-form">
          <input
            value={newName}
            placeholder={t("players.namePlaceholder")}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleInvite()}
            autoFocus
          />
          <button
            type="button"
            className="button-primary"
            onClick={handleInvite}
            disabled={!newName.trim() || createPlayer.isPending}
          >
            {t("players.createLink")}
          </button>
          <button
            type="button"
            className="button-ghost"
            onClick={() => setInviting(false)}
          >
            {t("common.cancel")}
          </button>
        </div>
      )}

      {players && players.length > 0 ? (
        <ul className="players-list">
          {players.map((player) => (
            <li key={player.id} className={player.revoked ? "revoked" : ""}>
              <div className="player-main">
                <span className="player-name">{player.name}</span>
                <span className="player-token">{player.token_prefix}…</span>
                {player.revoked && (
                  <span className="player-status">{t("players.revoked")}</span>
                )}
              </div>
              <div className="player-meta">
                <span>
                  {player.last_seen_at
                    ? t("players.lastSeen", {
                        when: new Date(player.last_seen_at).toLocaleString(),
                      })
                    : t("players.neverSeen")}
                </span>
                <span>{t("players.noteCount", { count: player.note_count })}</span>
              </div>
              <div className="player-actions">
                <button
                  type="button"
                  className="button-sm"
                  onClick={() => handleRotate(player)}
                  disabled={rotatePlayer.isPending}
                >
                  {t("players.rotate")}
                </button>
                {!player.revoked && (
                  <button
                    type="button"
                    className="button-sm button-ghost"
                    onClick={() => revokePlayer.mutate(player.id)}
                    disabled={revokePlayer.isPending}
                  >
                    {t("players.revoke")}
                  </button>
                )}
                <button
                  type="button"
                  className="icon-button icon-button-danger"
                  onClick={() => setDeleting(player)}
                  title={t("common.delete")}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="field-hint">{t("players.empty")}</p>
      )}

      {freshLink && (
        <div className="popover-backdrop" onClick={() => setFreshLink(null)}>
          <div className="player-link-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t("players.linkReady", { name: freshLink.name })}</h3>
            <p className="field-hint">{t("players.linkOnce")}</p>
            <div className="player-link-row">
              <input readOnly value={freshLink.play_url ?? ""} />
              <button
                type="button"
                className="button-sm"
                onClick={() =>
                  void navigator.clipboard.writeText(freshLink.play_url ?? "")
                }
              >
                {t("players.copy")}
              </button>
            </div>
            <button
              type="button"
              className="button-primary"
              onClick={() => setFreshLink(null)}
            >
              {t("common.close")}
            </button>
          </div>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title={t("players.deleteTitle", { name: deleting.name })}
          body={t("players.deleteBody")}
          confirmLabel={t("common.delete")}
          requireText={deleting.name}
          busy={deletePlayer.isPending}
          onConfirm={() =>
            deletePlayer.mutate(deleting.id, { onSuccess: () => setDeleting(null) })
          }
          onCancel={() => setDeleting(null)}
        />
      )}
    </section>
  );
}
