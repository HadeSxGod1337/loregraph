import { RoleSelect } from "./RoleSelect";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  changeUserRole,
  deleteUser,
  getOwnUserId,
  GoAuthError,
  listUsers,
  type UserSummary,
} from "../../lib/goAuth";
import { Icon } from "../ui/Icon";

interface UsersDialogProps {
  open: boolean;
  onClose: () => void;
}

/** Owner-only user administration. Loads the list on open, allows changing
 * each account's role through a select.
 *
 * The current user's row is not editable: the server refuses self-changes
 * unconditionally (an owner who demoted themselves could otherwise lock
 * the service out of role changes entirely), and disabling the control
 * here turns a 403-after-click into an obvious "not for you". */
export function UsersDialog({ open, onClose }: UsersDialogProps) {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<UserSummary | null>(null);
  const ownId = getOwnUserId();

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setUsers(null);
    setError(null);
    listUsers()
      .then((list) => {
        if (!cancelled) setUsers(list);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof GoAuthError && err.status === 403) {
          setError(t("users.error.forbidden"));
        } else {
          setError(t("users.error.load"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, t]);
  useEffect(() => {
    if (!confirmDelete) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setConfirmDelete(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [confirmDelete]);
  if (!open) return null;

  async function handleChange(user: UserSummary, nextRole: UserSummary["role"]) {
      if (!users) return;
      const previous = user.role;
      setBusyId(user.id);
      setUsers(
        users.map((u) => (u.id === user.id ? { ...u, role: nextRole } : u)),
      );
      try {
        await changeUserRole(user.id, nextRole);
      } catch (err) {
        setUsers(
          users.map((u) => (u.id === user.id ? { ...u, role: previous } : u)),
        );
        if (err instanceof GoAuthError && err.status === 403) {
          setError(t("users.error.forbidden"));
        } else {
          setError(t("users.error.change"));
        }
      } finally {
        setBusyId(null);
      }
    }
  async function handleDelete(user: UserSummary) {
    if (!users) return;
    setBusyId(user.id);
    try {
      await deleteUser(user.id);
      setUsers(users.filter((u) => u.id !== user.id));
      setConfirmDelete(null);
    } catch (err) {
      if (err instanceof GoAuthError && err.status === 403) {
        setError(t("users.error.forbidden"));
      } else {
        setError(t("users.error.delete"));
      }
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-card)",
          padding: 24,
          width: 560,
          minHeight: 360,
          maxHeight: "90vh",
          overflow: "auto",
          boxShadow: "var(--shadow)",
          position: "relative",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18 }}>{t("users.title")}</h2>
          <button
            type="button"
            className="button-ghost"
            onClick={onClose}
            aria-label={t("users.close")}
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        {error && (
          <div
            className="error-text"
            style={{
              background: "var(--bg-subtle)",
              border: "1px solid var(--danger)",
              borderRadius: "var(--radius-control)",
              padding: "8px 10px",
              fontSize: 13,
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}

        {users === null && !error && (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {t("users.loading")}
          </div>
        )}

        {users !== null && users.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {t("users.empty")}
          </div>
        )}

        {users !== null && users.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)", fontSize: 12 }}>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>
                  {t("users.col.email")}
                </th>
                <th style={{ textAlign: "left", padding: "4px 6px", width: 130 }}>
                  {t("users.col.role")}
                </th>
                <th style={{ width: 32 }} />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const isSelf = user.id === ownId;
                return (
                  <tr
                    key={user.id}
                    style={{ borderTop: "1px solid var(--border)" }}
                  >
                    <td style={{ padding: "8px 6px", fontSize: 13 }}>
                      {user.email}
                      {isSelf && (
                        <span
                          style={{
                            marginLeft: 6,
                            color: "var(--text-muted)",
                            fontSize: 12,
                          }}
                        >
                          {t("users.self")}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      <RoleSelect
                        value={user.role}
                        disabled={isSelf || busyId === user.id}
                        onChange={(role) => handleChange(user, role)}
                      />
                    </td>
                    <td style={{ padding: "8px 0", width: 32 }}>
                      {!isSelf && (
                        <button
                          type="button"
                          className="button-ghost"
                          onClick={() => setConfirmDelete(user)}
                          disabled={busyId === user.id}
                          title={t("users.delete")}
                          aria-label={t("users.delete")}
                          style={{
                            padding: 4,
                            color: "var(--danger)",
                          }}
                        >
                          <Icon name="trash" size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
              {confirmDelete && (
          <div
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.55)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1200,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-card)",
                padding: 20,
                width: 360,
                boxShadow: "var(--shadow)",
                fontSize: 13,
              }}
            >
              <div style={{ marginBottom: 14 }}>
                {t("users.confirmDelete", { email: confirmDelete.email })}
              </div>
              <div
                style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
              >
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => setConfirmDelete(null)}
                  disabled={busyId === confirmDelete.id}
                >
                  {t("users.cancel")}
                </button>
                <button
                  type="button"
                  className="button-danger-solid"
                  onClick={() => handleDelete(confirmDelete)}
                  disabled={busyId === confirmDelete.id}
                >
                  {t("users.deleteConfirm")}
                </button>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}