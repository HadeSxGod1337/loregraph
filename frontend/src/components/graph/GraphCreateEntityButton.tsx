import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Entity } from "../../api/types";
import { DEFAULT_ENTITY_TYPES } from "../../api/types";
import { useDismiss } from "../../hooks/useDismiss";
import { useCreateEntity } from "../../hooks/useEntities";
import { Icon } from "../ui/Icon";

interface GraphCreateEntityButtonProps {
  projectId: string;
  onCreated: (entity: Entity) => void;
}

export function GraphCreateEntityButton({ projectId, onCreated }: GraphCreateEntityButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState("npc");
  const [title, setTitle] = useState("");
  const createEntity = useCreateEntity(projectId);
  const popoverRef = useRef<HTMLFormElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  useDismiss(open, popoverRef, () => setOpen(false));

  useEffect(() => {
    if (open) titleRef.current?.focus();
  }, [open]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    createEntity.mutate(
      { type, title: title.trim(), fields: [] },
      {
        onSuccess: (created) => {
          setOpen(false);
          setTitle("");
          setType("npc");
          onCreated(created);
        },
      },
    );
  }

  return (
    <>
      <button
        type="button"
        className="graph-create-fab"
        onClick={() => setOpen(true)}
        aria-label={t("graph.createEntity")}
      >
        <Icon name="plus" size={22} />
      </button>

      {open && (
        <div className="popover-backdrop" onClick={() => setOpen(false)}>
          <form
            className="graph-create-popover"
            ref={popoverRef}
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleSubmit}
          >
            <h3>{t("graph.createEntityTitle")}</h3>
            <label>
              {t("graph.typeLabel")}
              <input
                list="graph-entity-type-suggestions"
                value={type}
                onChange={(e) => setType(e.target.value)}
              />
              <datalist id="graph-entity-type-suggestions">
                {DEFAULT_ENTITY_TYPES.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </label>
            <label>
              {t("graph.titleLabel")}
              <input
                ref={titleRef}
                placeholder={t("graph.titlePlaceholder")}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <div className="graph-create-popover-actions">
              <button type="submit" disabled={!title.trim() || createEntity.isPending}>
                {t("common.create")}
              </button>
              <button type="button" onClick={() => setOpen(false)}>
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
