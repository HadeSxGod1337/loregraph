import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { EntityTemplate } from "../../api/types";
import { useTemplates } from "../../hooks/useTemplates";
import { Icon } from "../ui/Icon";

interface TemplateSelectProps {
  projectId: string;
  value: string | null;
  onSelect: (template: EntityTemplate | null) => void;
}

/** Picks the template an entity is bound to (or none). Selecting a template is
 * opt-in — entities without one keep the plain field list. */
export function TemplateSelect({ projectId, value, onSelect }: TemplateSelectProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: templates } = useTemplates(projectId);

  return (
    <div className="template-select">
      <label>
        {t("templates.templateLabel")}
        <select
          value={value ?? ""}
          onChange={(e) => {
            const id = e.target.value;
            onSelect(
              id === "" ? null : (templates ?? []).find((tpl) => tpl.id === id) ?? null,
            );
          }}
        >
          <option value="">{t("templates.none")}</option>
          {(templates ?? []).map((tpl) => (
            <option key={tpl.id} value={tpl.id}>
              {tpl.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="button-sm"
        onClick={() => navigate(`/projects/${projectId}/settings?section=templates`)}
      >
        <Icon name="layers" size={13} />
        {t("templates.manage")}
      </button>
    </div>
  );
}
