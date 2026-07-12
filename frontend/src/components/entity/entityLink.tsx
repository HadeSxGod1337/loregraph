import type { AnyExtension } from "@tiptap/core";
import Image from "@tiptap/extension-image";
import Mention, { type MentionOptions } from "@tiptap/extension-mention";
import Underline from "@tiptap/extension-underline";
import {
  NodeViewWrapper,
  ReactNodeViewRenderer,
  ReactRenderer,
  type NodeViewProps,
} from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import type { SuggestionKeyDownProps, SuggestionProps } from "@tiptap/suggestion";
import { useQuery } from "@tanstack/react-query";
import { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMatch } from "react-router-dom";

import { entitiesApi } from "../../api/entities";
import type { Entity } from "../../api/types";
import { useEntityNavigation } from "../EntityNavigationContext";

const SUGGESTION_LIMIT = 8;

interface EntityLinkAttrs {
  entityId: string;
  fieldKey: string | null;
  label: string;
}

/** Clickable wikilink chip. The title is resolved live by entityId (a stored
 * label goes stale the moment the target is renamed); the stored label is
 * only the fallback for deleted targets, rendered as a broken link. */
function EntityLinkChip({ node }: NodeViewProps) {
  const { t } = useTranslation();
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId;
  const navigateToEntity = useEntityNavigation();
  const attrs = node.attrs as EntityLinkAttrs;

  const { data: entities } = useQuery({
    queryKey: ["entities", projectId, undefined],
    queryFn: () => entitiesApi.list(projectId!),
    enabled: Boolean(projectId),
  });

  const entity = entities?.find((e) => e.id === attrs.entityId);
  const broken = entities !== undefined && entity === undefined;
  const label = entity?.title ?? attrs.label ?? t("entityLink.unknown");

  return (
    <NodeViewWrapper as="span" className="entity-link-wrapper">
      <button
        type="button"
        className={broken ? "entity-link-chip broken" : "entity-link-chip"}
        disabled={broken}
        title={broken ? t("entityLink.brokenTitle") : t("entityLink.goTo", { label })}
        onClick={() => navigateToEntity(attrs.entityId)}
      >
        {label}
      </button>
    </NodeViewWrapper>
  );
}

export const EntityLink = Mention.extend<MentionOptions<Entity, EntityLinkAttrs>>({
  name: "entityLink",

  addAttributes() {
    return {
      entityId: { default: "" },
      fieldKey: { default: null },
      label: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-entity-link]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      { "data-entity-link": "", ...HTMLAttributes },
      `[[${(node.attrs as EntityLinkAttrs).label}]]`,
    ];
  },

  renderText({ node }) {
    return `[[${(node.attrs as EntityLinkAttrs).label}]]`;
  },

  addNodeView() {
    return ReactNodeViewRenderer(EntityLinkChip);
  },
});

interface SuggestionListHandle {
  onKeyDown: (props: SuggestionKeyDownProps) => boolean;
}

interface SuggestionListProps {
  items: Entity[];
  command: (attrs: EntityLinkAttrs) => void;
}

const SuggestionList = forwardRef<SuggestionListHandle, SuggestionListProps>(
  function SuggestionList({ items, command }, ref) {
    const { t } = useTranslation();
    const [selectedIndex, setSelectedIndex] = useState(0);

    useEffect(() => setSelectedIndex(0), [items]);

    function select(index: number) {
      const item = items[index];
      if (item) {
        command({ entityId: item.id, fieldKey: null, label: item.title });
      }
    }

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }) => {
        if (items.length === 0) return false;
        if (event.key === "ArrowUp") {
          setSelectedIndex((i) => (i + items.length - 1) % items.length);
          return true;
        }
        if (event.key === "ArrowDown") {
          setSelectedIndex((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === "Enter") {
          select(selectedIndex);
          return true;
        }
        return false;
      },
    }));

    if (items.length === 0) {
      return <div className="entity-link-suggestions-empty">{t("entityLink.noMatches")}</div>;
    }
    return (
      <ul className="entity-link-suggestions-list">
        {items.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              className={index === selectedIndex ? "selected" : undefined}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => select(index)}
            >
              <span className="entity-link-suggestion-title">{item.title}</span>
              <span className="entity-link-suggestion-type">{item.type}</span>
            </button>
          </li>
        ))}
      </ul>
    );
  },
);

function suggestionConfig(projectId: string | undefined) {
  return {
    char: "[[",
    allowSpaces: true,
    items: async ({ query }: { query: string }): Promise<Entity[]> => {
      if (!projectId) return [];
      const entities = await entitiesApi.list(projectId);
      const needle = query.toLowerCase();
      return entities
        .filter((e) => e.title.toLowerCase().includes(needle))
        .slice(0, SUGGESTION_LIMIT);
    },
    command: ({
      editor,
      range,
      props,
    }: {
      editor: SuggestionProps<Entity>["editor"];
      range: SuggestionProps<Entity>["range"];
      props: EntityLinkAttrs;
    }) => {
      editor
        .chain()
        .focus()
        .insertContentAt(range, [
          { type: "entityLink", attrs: props },
          { type: "text", text: " " },
        ])
        .run();
    },
    render: () => {
      let component: ReactRenderer<SuggestionListHandle, SuggestionListProps> | null =
        null;
      let container: HTMLDivElement | null = null;

      function position(clientRect: DOMRect | null | undefined) {
        if (!container || !clientRect) return;
        container.style.left = `${clientRect.left + window.scrollX}px`;
        container.style.top = `${clientRect.bottom + window.scrollY + 4}px`;
      }

      return {
        onStart(props: SuggestionProps<Entity, EntityLinkAttrs>) {
          component = new ReactRenderer(SuggestionList, {
            props: { items: props.items, command: props.command },
            editor: props.editor,
          });
          container = document.createElement("div");
          container.className = "entity-link-suggestions";
          container.appendChild(component.element);
          document.body.appendChild(container);
          position(props.clientRect?.());
        },
        onUpdate(props: SuggestionProps<Entity, EntityLinkAttrs>) {
          component?.updateProps({ items: props.items, command: props.command });
          position(props.clientRect?.());
        },
        onKeyDown(props: SuggestionKeyDownProps): boolean {
          if (props.event.key === "Escape") {
            container?.remove();
            container = null;
            return true;
          }
          return component?.ref?.onKeyDown(props) ?? false;
        },
        onExit() {
          container?.remove();
          component?.destroy();
          container = null;
          component = null;
        },
      };
    },
  };
}

/** The single extension list shared by the editor (RichTextField) and the
 * read-only view (RichTextView) — the two must never diverge, or documents
 * would render differently between editing and viewing. */
export function buildRichTextExtensions(
  projectId: string | undefined,
): AnyExtension[] {
  return [
    StarterKit,
    Image,
    Underline,
    EntityLink.configure({ suggestion: suggestionConfig(projectId) }),
  ];
}
