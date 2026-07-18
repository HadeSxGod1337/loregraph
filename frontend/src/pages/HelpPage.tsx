import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Icon, type IconName } from "../components/ui/Icon";

interface HelpTopic {
  id: string;
  icon: IconName;
  titleKey: string;
  bodyKey: string;
}

interface HelpSection {
  id: string;
  icon: IconName;
  titleKey: string;
  leadKey: string;
  topics: HelpTopic[];
}

const SECTIONS: HelpSection[] = [
  {
    id: "basics",
    icon: "layers",
    titleKey: "help.basics.title",
    leadKey: "help.basics.lead",
    topics: [
      { id: "projects", icon: "folder", titleKey: "help.basics.projects.title", bodyKey: "help.basics.projects.body" },
      { id: "entities", icon: "layers", titleKey: "help.basics.entities.title", bodyKey: "help.basics.entities.body" },
      { id: "fields", icon: "settings", titleKey: "help.basics.fields.title", bodyKey: "help.basics.fields.body" },
      { id: "icons", icon: "appearance", titleKey: "help.basics.icons.title", bodyKey: "help.basics.icons.body" },
    ],
  },
  {
    id: "graph",
    icon: "network",
    titleKey: "help.graph.title",
    leadKey: "help.graph.lead",
    topics: [
      { id: "modes", icon: "expand", titleKey: "help.graph.modes.title", bodyKey: "help.graph.modes.body" },
      { id: "navigating", icon: "search", titleKey: "help.graph.navigating.title", bodyKey: "help.graph.navigating.body" },
      { id: "filters", icon: "filter", titleKey: "help.graph.filters.title", bodyKey: "help.graph.filters.body" },
    ],
  },
  {
    id: "assistant",
    icon: "sparkles",
    titleKey: "help.assistant.title",
    leadKey: "help.assistant.lead",
    topics: [
      { id: "setup", icon: "settings", titleKey: "help.assistant.setup.title", bodyKey: "help.assistant.setup.body" },
      { id: "chat", icon: "sparkles", titleKey: "help.assistant.chat.title", bodyKey: "help.assistant.chat.body" },
      { id: "review", icon: "check", titleKey: "help.assistant.review.title", bodyKey: "help.assistant.review.body" },
    ],
  },
  {
    id: "knowledge",
    icon: "paperclip",
    titleKey: "help.knowledge.title",
    leadKey: "help.knowledge.lead",
    topics: [
      { id: "upload", icon: "upload", titleKey: "help.knowledge.upload.title", bodyKey: "help.knowledge.upload.body" },
    ],
  },
  {
    id: "integrations",
    icon: "plug",
    titleKey: "help.integrations.title",
    leadKey: "help.integrations.lead",
    topics: [
      { id: "obsidian", icon: "folder", titleKey: "help.integrations.obsidian.title", bodyKey: "help.integrations.obsidian.body" },
      { id: "foundry", icon: "plug", titleKey: "help.integrations.foundry.title", bodyKey: "help.integrations.foundry.body" },
      { id: "lss", icon: "external-link", titleKey: "help.integrations.lss.title", bodyKey: "help.integrations.lss.body" },
    ],
  },
  {
    id: "settings",
    icon: "settings",
    titleKey: "help.settings.title",
    leadKey: "help.settings.lead",
    topics: [
      { id: "instructions", icon: "sparkles", titleKey: "help.settings.instructions.title", bodyKey: "help.settings.instructions.body" },
      { id: "reindex", icon: "refresh", titleKey: "help.settings.reindex.title", bodyKey: "help.settings.reindex.body" },
    ],
  },
];

// The special "show everything" entry — not a real section, so it isn't
// part of SECTIONS; the content pane falls back to rendering all of them
// whenever this id is active.
const OVERVIEW_ID = "overview";

/** In-app manual: a table of contents on the left picks what the right
 * column shows. "Справка" (the first entry) renders every section back to
 * back for a skim-everything read; clicking any other entry narrows the
 * content pane down to just that one section.
 *
 * This used to be a single long page with scroll-position tracking
 * (IntersectionObserver, then a manual scroll listener) driving the active
 * highlight — it fought the fixed top bar for scroll-margin, required a
 * padded dead zone at the bottom so the last section could ever become
 * "active", and needed sub-pixel slack to match its own anchor jumps.
 * Selection-driven content (click sets what's rendered, not where the page
 * scrolls to) has none of that: the active item is exactly the one that
 * was clicked, always. */
export function HelpPage() {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState<string>(OVERVIEW_ID);

  // Switching sections swaps the content pane's height; start the reader
  // at its top rather than leaving them wherever the previous pane's
  // scroll position happened to land.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [activeId]);

  const activeSection = SECTIONS.find((section) => section.id === activeId);
  const visibleSections = activeSection ? [activeSection] : SECTIONS;

  return (
    <div className="help-page">
      <header className="help-hero">
        <h1>
          <Icon name="help" size={24} />
          {t("help.title")}
        </h1>
        <p>{t("help.subtitle")}</p>
      </header>

      <div className="help-layout">
        <nav className="help-toc" aria-label={t("help.tocLabel")}>
          <button
            type="button"
            className={"help-toc-item" + (activeId === OVERVIEW_ID ? " active" : "")}
            onClick={() => setActiveId(OVERVIEW_ID)}
          >
            <Icon name="help" size={15} />
            {t("help.title")}
          </button>
          {SECTIONS.map((section) => (
            <button
              type="button"
              key={section.id}
              className={"help-toc-item" + (activeId === section.id ? " active" : "")}
              onClick={() => setActiveId(section.id)}
            >
              <Icon name={section.icon} size={15} />
              {t(section.titleKey)}
            </button>
          ))}
        </nav>

        <div className="help-content">
          {visibleSections.map((section) => (
            <section key={section.id} className="help-section">
              <div className="help-section-heading">
                <span className="help-section-icon">
                  <Icon name={section.icon} size={18} />
                </span>
                <div>
                  <h2>{t(section.titleKey)}</h2>
                  <p className="help-section-lead">{t(section.leadKey)}</p>
                </div>
              </div>

              <div className="help-topic-grid">
                {section.topics.map((topic) => (
                  <article key={topic.id} className="help-topic-card">
                    <h3>
                      <Icon name={topic.icon} size={14} />
                      {t(topic.titleKey)}
                    </h3>
                    <p>{t(topic.bodyKey)}</p>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
