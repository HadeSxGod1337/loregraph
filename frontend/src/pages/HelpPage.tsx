import { useEffect, useRef, useState } from "react";
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

/** In-app manual: a sticky table of contents on the left tracks scroll
 * position (IntersectionObserver, no libraries) while the right column
 * reads as a sequence of short, scannable cards — one per topic, not one
 * wall of text per section. */
export function HelpPage() {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState(SECTIONS[0].id);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;
    const headings = Array.from(root.querySelectorAll("[data-section-heading]"));
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) {
          setActiveId((visible[0].target as HTMLElement).dataset.sectionHeading!);
        }
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 },
    );
    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="help-page">
      <header className="help-hero">
        <Icon name="sparkles" size={28} />
        <h1>{t("help.title")}</h1>
        <p>{t("help.subtitle")}</p>
      </header>

      <div className="help-layout">
        <nav className="help-toc" aria-label={t("help.tocLabel")}>
          {SECTIONS.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className={"help-toc-item" + (activeId === section.id ? " active" : "")}
            >
              <Icon name={section.icon} size={15} />
              {t(section.titleKey)}
            </a>
          ))}
        </nav>

        <div className="help-content" ref={contentRef}>
          {SECTIONS.map((section) => (
            <section key={section.id} className="help-section">
              <div
                className="help-section-heading"
                id={section.id}
                data-section-heading={section.id}
              >
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
