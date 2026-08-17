import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FEEDBACK_FORM_EMBED_URL, FEEDBACK_FORM_URL } from "../../lib/externalLinks";
import { ExternalPageDrawer } from "../help/ExternalPageDrawer";
import { Icon } from "../ui/Icon";

interface SidebarFeedbackButtonProps {
  collapsed: boolean;
}

/** Compact escape hatch to the public feedback form, next to the theme
 * toggle — unlike Help, this has nothing to do with the open project, so it
 * doesn't wait for one to exist. Opens the same drawer HelpPage's support
 * block does, just pre-aimed at feedback. */
export function SidebarFeedbackButton({ collapsed }: SidebarFeedbackButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const label = t("nav.feedback");

  return (
    <>
      <button
        type="button"
        className="sidebar-nav-item sidebar-feedback-btn"
        title={collapsed ? label : undefined}
        aria-label={label}
        onClick={() => setOpen(true)}
      >
        <Icon name="message-square" size={17} className="sidebar-nav-icon" />
        {!collapsed && <span className="sidebar-nav-label">{label}</span>}
      </button>
      {open && (
        <ExternalPageDrawer
          title={t("help.support.feedbackTitle")}
          url={FEEDBACK_FORM_URL}
          embedUrl={FEEDBACK_FORM_EMBED_URL}
          allowForms
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
