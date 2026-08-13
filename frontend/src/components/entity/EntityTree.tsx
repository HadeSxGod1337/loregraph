import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useCallback, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { TreeExpansion } from "../../hooks/useTreeExpansion";
import { pathKey, type FilteredNode } from "../../lib/hierarchy";
import { EntityTreeRow } from "./EntityTreeRow";

/** The mouse has to travel this far before the row starts moving — below it
 * the gesture is still a click, and rows are links first. */
const DRAG_START_DISTANCE_PX = 6;
/** On touch the same job is done by a hold, so that a finger dragged up the
 * page still scrolls the list instead of picking a row up. */
const TOUCH_HOLD_MS = 250;
const TOUCH_HOLD_TOLERANCE_PX = 6;

interface EntityTreeProps {
  projectId: string;
  nodes: FilteredNode[];
  expansion: TreeExpansion;
  /** While a search is running everything is shown open, without writing that
   * over what the DM collapsed by hand. */
  forceOpen?: boolean;
  /** Dropping a row on another row asks for the containment edge that would
   * nest it there. Omitted → the tree is read-only and nothing drags. */
  onNest?: (childEntityId: string, parentEntityId: string) => void;
  /** Whether that edge is allowed, for highlighting the row under the pointer
   * (a folder cannot move into its own member). */
  canNest?: (childEntityId: string, parentEntityId: string) => boolean;
}

/** The entity list as a folder tree: a faction with `contains` members shows
 * them nested underneath instead of scattered across the flat list.
 *
 * Keyboard follows the ARIA tree pattern — one row is in the tab order, the
 * arrows move within the tree. Rows themselves stay links, so middle-click and
 * ctrl-click still open a card in a new tab. */
export function EntityTree({
  projectId,
  nodes,
  expansion,
  forceOpen = false,
  onNest,
  canNest,
}: EntityTreeProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const rootRef = useRef<HTMLUListElement>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [dragged, setDragged] = useState<{ id: string; title: string } | null>(null);

  // Pointer only. Keyboard dragging would have to take Space and Enter away
  // from the tree pattern above; the same edge is created from the keyboard on
  // the entity page, where relationships are edited as a list.
  const sensors = useSensors(
    useSensor(MouseSensor, {
      activationConstraint: { distance: DRAG_START_DISTANCE_PX },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: TOUCH_HOLD_MS,
        tolerance: TOUCH_HOLD_TOLERANCE_PX,
      },
    }),
  );

  /** Rows currently on screen, in visual order — the DOM is the only place
   * that knows what a collapsed branch hid. */
  const visibleItems = useCallback((): HTMLLIElement[] => {
    if (!rootRef.current) return [];
    return [...rootRef.current.querySelectorAll<HTMLLIElement>('li[role="treeitem"]')];
  }, []);

  const focusItem = useCallback((item: HTMLLIElement | undefined) => {
    if (!item) return;
    setActiveKey(item.dataset.treeKey ?? null);
    item.focus();
  }, []);

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLUListElement>) => {
      const item = (event.target as HTMLElement).closest<HTMLLIElement>(
        'li[role="treeitem"]',
      );
      if (!item) return;
      const key = item.dataset.treeKey;
      if (!key) return;
      const items = visibleItems();
      const index = items.indexOf(item);
      const isFolder = item.getAttribute("aria-expanded") !== null;
      const isOpen = item.getAttribute("aria-expanded") === "true";

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          focusItem(items[index + 1]);
          break;
        case "ArrowUp":
          event.preventDefault();
          focusItem(items[index - 1]);
          break;
        case "ArrowRight":
          event.preventDefault();
          if (isFolder && !isOpen) expansion.toggle(key);
          else if (isFolder) focusItem(items[index + 1]);
          break;
        case "ArrowLeft": {
          event.preventDefault();
          if (isFolder && isOpen) {
            expansion.toggle(key);
            break;
          }
          const parent = item.parentElement?.closest<HTMLLIElement>(
            'li[role="treeitem"]',
          );
          focusItem(parent ?? undefined);
          break;
        }
        case "Home":
          event.preventDefault();
          focusItem(items[0]);
          break;
        case "End":
          event.preventDefault();
          focusItem(items[items.length - 1]);
          break;
        case " ":
          if (isFolder) {
            event.preventDefault();
            expansion.toggle(key);
          }
          break;
        case "Enter": {
          // Enter opens the card even on a folder — space is what folds it.
          const entityId = item.dataset.entityId;
          if (entityId) {
            event.preventDefault();
            navigate(`/projects/${projectId}/entities/${entityId}`);
          }
          break;
        }
        default:
          break;
      }
    },
    [expansion, focusItem, navigate, projectId, visibleItems],
  );

  const firstKey = nodes.length > 0 ? pathKey(nodes[0].path) : null;

  const handleDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current as DragData | undefined;
    if (data) setDragged({ id: data.entityId, title: data.title });
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setDragged(null);
    const child = event.active.data.current as DragData | undefined;
    const parent = event.over?.data.current as DragData | undefined;
    if (!child || !parent || child.entityId === parent.entityId) return;
    onNest?.(child.entityId, parent.entityId);
  };

  const tree = (
    <ul
      className="entity-list entity-tree"
      role="tree"
      aria-label={t("entities.title")}
      ref={rootRef}
      onKeyDown={onKeyDown}
    >
      {nodes.map((node) => (
        <TreeItem
          key={pathKey(node.path)}
          projectId={projectId}
          node={node}
          level={1}
          expansion={expansion}
          forceOpen={forceOpen}
          activeKey={activeKey ?? firstKey}
          onFocusItem={setActiveKey}
          draggable={onNest !== undefined}
          draggedId={dragged?.id ?? null}
          canNest={canNest}
        />
      ))}
    </ul>
  );

  if (!onNest) return tree;

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setDragged(null)}
    >
      {tree}
      <DragOverlay dropAnimation={null}>
        {dragged && <span className="entity-tree-drag-chip">{dragged.title}</span>}
      </DragOverlay>
    </DndContext>
  );
}

interface DragData {
  entityId: string;
  title: string;
}

interface TreeItemProps {
  projectId: string;
  node: FilteredNode;
  level: number;
  expansion: TreeExpansion;
  forceOpen: boolean;
  /** The one row in the page's tab order (roving tabindex). */
  activeKey: string | null;
  onFocusItem: (key: string) => void;
  draggable: boolean;
  draggedId: string | null;
  canNest?: (childEntityId: string, parentEntityId: string) => boolean;
}

function TreeItem({
  projectId,
  node,
  level,
  expansion,
  forceOpen,
  activeKey,
  onFocusItem,
  draggable,
  draggedId,
  canNest,
}: TreeItemProps) {
  const key = pathKey(node.path);
  const hasChildren = node.children.length > 0;
  const open = hasChildren && (forceOpen || expansion.isOpen(key));
  const memberTypes = [...new Set(node.children.map((child) => child.entity.type))];
  const dragData: DragData = { entityId: node.entity.id, title: node.entity.title };

  const { setNodeRef: setDragRef, listeners, isDragging } = useDraggable({
    id: `drag:${key}`,
    data: dragData,
    disabled: !draggable,
  });
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop:${key}`,
    data: dragData,
    disabled: !draggable,
  });
  const setRowRef = useCallback(
    (element: HTMLDivElement | null) => {
      setDragRef(element);
      setDropRef(element);
    },
    [setDragRef, setDropRef],
  );

  const dropAllowed =
    isOver &&
    draggedId !== null &&
    draggedId !== node.entity.id &&
    (canNest?.(draggedId, node.entity.id) ?? true);
  const rowClass = useMemo(
    () =>
      [
        "entity-tree-drag",
        isDragging ? "is-dragging" : "",
        dropAllowed ? "is-drop-target" : "",
        isOver && !dropAllowed ? "is-drop-blocked" : "",
      ]
        .filter(Boolean)
        .join(" "),
    [dropAllowed, isDragging, isOver],
  );

  return (
    <li
      role="treeitem"
      // Without an explicit name a treeitem is named by its contents — for a
      // folder that would be the whole branch read out as one label.
      aria-label={node.entity.title}
      aria-expanded={hasChildren ? open : undefined}
      aria-level={level}
      tabIndex={activeKey === key ? 0 : -1}
      data-tree-key={key}
      data-entity-id={node.entity.id}
      onFocus={() => onFocusItem(key)}
      className="entity-tree-node"
    >
      {/* The wrapper carries the drag/drop refs so the row markup itself stays
          the same element in every view. onDragStart kills the browser's own
          link dragging, which would otherwise fight the pointer sensor. */}
      <div
        ref={setRowRef}
        className={rowClass}
        onDragStart={(event) => event.preventDefault()}
        {...listeners}
      >
        <EntityTreeRow
          projectId={projectId}
          entity={node.entity}
          childCount={node.children.length}
          memberTypes={memberTypes}
          open={open}
          onToggle={() => expansion.toggle(key)}
          context={!node.matches}
          parentCount={node.parentCount}
        />
      </div>
      {hasChildren && open && (
        <ul role="group" className="entity-tree-group">
          {node.children.map((child) => (
            <TreeItem
              key={pathKey(child.path)}
              projectId={projectId}
              node={child}
              level={level + 1}
              expansion={expansion}
              forceOpen={forceOpen}
              activeKey={activeKey}
              onFocusItem={onFocusItem}
              draggable={draggable}
              draggedId={draggedId}
              canNest={canNest}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
