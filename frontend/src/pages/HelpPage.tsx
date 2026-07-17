import { useTranslation } from "react-i18next";

type Section = {
  key: string;
  bodyKey: string;
  children?: Section[];
};

const SECTIONS: Section[] = [
  { key: "gettingStarted", bodyKey: "gettingStartedBody" },
  { key: "creatingProject", bodyKey: "creatingProjectBody" },
  {
    key: "entities",
    bodyKey: "entitiesBody",
    children: [
      { key: "entityTypes", bodyKey: "entityTypesBody" },
      { key: "entityFields", bodyKey: "entityFieldsBody" },
      { key: "entityIcons", bodyKey: "entityIconsBody" },
    ],
  },
  {
    key: "graphView",
    bodyKey: "graphViewBody",
    children: [
      { key: "focusedMode", bodyKey: "focusedMode" },
      { key: "allMode", bodyKey: "allMode" },
      { key: "graphInteractions", bodyKey: "graphInteractions" },
    ],
  },
  {
    key: "aiAssistant",
    bodyKey: "aiAssistantBody",
    children: [
      { key: "assistantSetup", bodyKey: "assistantSetupBody" },
      { key: "assistantChat", bodyKey: "assistantChatBody" },
      { key: "assistantDrafts", bodyKey: "assistantDraftsBody" },
      { key: "draftActions", bodyKey: "draftActions" },
    ],
  },
  { key: "knowledgeBase", bodyKey: "knowledgeBaseBody" },
  {
    key: "integrations",
    bodyKey: "integrationsBody",
    children: [
      { key: "integrationObsidian", bodyKey: "integrationObsidian" },
      { key: "integrationFoundry", bodyKey: "integrationFoundry" },
      { key: "integrationLss", bodyKey: "integrationLss" },
    ],
  },
  {
    key: "settings",
    bodyKey: "settingsBody",
    children: [
      { key: "settingsGeneral", bodyKey: "settingsGeneral" },
      { key: "settingsAgent", bodyKey: "settingsAgent" },
      { key: "settingsKnowledge", bodyKey: "settingsKnowledge" },
      { key: "settingsIntegrations", bodyKey: "settingsIntegrations" },
      { key: "settingsUsage", bodyKey: "settingsUsage" },
    ],
  },
];

export function HelpPage() {
  const { t } = useTranslation();

  function renderSection(section: Section, depth = 0) {
    const Tag = depth === 0 ? ("h2" as const) : ("li" as const);
    return (
      <div key={section.key} className="help-section">
        <Tag>
          <a href={`#${section.key}`}>{t(`help.${section.key}`)}</a>
        </Tag>
        <p>{t(`help.${section.bodyKey}`)}</p>
        {section.children && (
          <ul className="help-subsections">
            {section.children.map((child) => renderSection(child, depth + 1))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div className="help-page">
      <h1>{t("help.title")}</h1>

      <nav className="help-toc">
        <h3>{t("help.toc")}</h3>
        <ul>
          {SECTIONS.map((s) => (
            <li key={s.key}>
              <a href={`#${s.key}`}>{t(`help.${s.key}`)}</a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="help-content">{SECTIONS.map((s) => renderSection(s))}</div>
    </div>
  );
}
