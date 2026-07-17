import type { TFunction } from "i18next";

export interface HelpSection {
  id: string;
  heading: string;
  body: string;
}

/**
 * Build the help page sections from i18n keys. Called at render time so
 * the content follows the active language.
 */
export function getHelpSections(t: TFunction): HelpSection[] {
  return [
    {
      id: "getting-started",
      heading: t("help.gettingStarted"),
      body: t("help.gettingStartedBody"),
    },
    {
      id: "creating-project",
      heading: t("help.creatingProject"),
      body: t("help.creatingProjectBody"),
    },
    {
      id: "entities",
      heading: t("help.entities"),
      body: t("help.entitiesBody"),
    },
    {
      id: "entity-types",
      heading: t("help.entityTypes"),
      body: t("help.entityTypesBody"),
    },
    {
      id: "entity-fields",
      heading: t("help.entityFields"),
      body: t("help.entityFieldsBody"),
    },
    {
      id: "entity-icons",
      heading: t("help.entityIcons"),
      body: t("help.entityIconsBody"),
    },
    {
      id: "graph-view",
      heading: t("help.graphView"),
      body: t("help.graphViewBody"),
    },
    {
      id: "focused-mode",
      heading: t("help.focusedMode"),
      body: "", // combined with graph-view via subheading
    },
    {
      id: "all-mode",
      heading: t("help.allMode"),
      body: "",
    },
    {
      id: "graph-interactions",
      heading: t("help.graphInteractions"),
      body: "",
    },
    {
      id: "ai-assistant",
      heading: t("help.aiAssistant"),
      body: t("help.aiAssistantBody"),
    },
    {
      id: "assistant-setup",
      heading: t("help.assistantSetup"),
      body: t("help.assistantSetupBody"),
    },
    {
      id: "assistant-chat",
      heading: t("help.assistantChat"),
      body: t("help.assistantChatBody"),
    },
    {
      id: "assistant-drafts",
      heading: t("help.assistantDrafts"),
      body: t("help.assistantDraftsBody"),
    },
    {
      id: "draft-review-list",
      heading: "",
      body: t("help.draftReviewList"),
    },
    {
      id: "draft-actions",
      heading: "",
      body: t("help.draftActions"),
    },
    {
      id: "knowledge-base",
      heading: t("help.knowledgeBase"),
      body: t("help.knowledgeBaseBody"),
    },
    {
      id: "integrations",
      heading: t("help.integrations"),
      body: t("help.integrationsBody"),
    },
    {
      id: "integration-obsidian",
      heading: "",
      body: t("help.integrationObsidian"),
    },
    {
      id: "integration-foundry",
      heading: "",
      body: t("help.integrationFoundry"),
    },
    {
      id: "integration-lss",
      heading: "",
      body: t("help.integrationLss"),
    },
    {
      id: "settings",
      heading: t("help.settings"),
      body: t("help.settingsBody"),
    },
    {
      id: "settings-general",
      heading: "",
      body: t("help.settingsGeneral"),
    },
    {
      id: "settings-agent",
      heading: "",
      body: t("help.settingsAgent"),
    },
    {
      id: "settings-knowledge",
      heading: "",
      body: t("help.settingsKnowledge"),
    },
    {
      id: "settings-integrations",
      heading: "",
      body: t("help.settingsIntegrations"),
    },
    {
      id: "settings-usage",
      heading: "",
      body: t("help.settingsUsage"),
    },
  ];
}
