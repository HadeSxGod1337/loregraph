import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  horizontalListSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type {
  Entity,
  EntityTemplateCreate,
  FieldType,
  RegionKind,
  SheetBlock,
  SheetContainer,
  SheetLayout,
  SheetPreset,
  SheetRegion,
  SheetSection,
  TemplateFieldDef,
  WidgetType,
} from "../../../api/types";
import { useCreateSheetPreset, useSheetPresets } from "../../../hooks/useSheetPresets";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Icon } from "../../ui/Icon";
import { emptyValue } from "../applyTemplate";
import { SheetRenderer } from "../SheetRenderer";
import {
  DEFAULT_STAT_MOD_FORMULA,
  FormulaSyntaxError,
  parseDependencies,
} from "../widgets/formula";
import {
  addBlock,
  addContainer,
  addRegion,
  addSection,
  allBlocks,
  containerIds,
  ensureIds,
  findContainerOfBlock,
  getBlocks,
  insertPreset,
  moveBlock,
  moveContainer,
  moveRegion,
  removeBlock,
  removeContainer,
  removeFieldCascade,
  removeRegion,
  removeSection,
  renameContainer,
  renameRegion,
  setRegionKind,
  updateBlock,
  updateSection,
} from "./layoutOps";
import {
  defaultWidgetForFieldType,
  WIDGET_META,
  WIDGET_TYPES,
  widgetsForFieldType,
} from "../widgets/registry";

/** Drag scopes. Every draggable/droppable carries one of these in its dnd-kit
 * `data`, and `collisionDetection` below only ever considers droppables whose
 * type the active drag accepts — without that filter a region drag resolves
 * against a nested block's rect (they all live in one DndContext) and nothing
 * lands where the DM aimed it. */
type DragType = "region" | "container" | "block" | "palette-field";

const ACCEPTS: Record<DragType, string[]> = {
  region: ["region"],
  container: ["container"],
  block: ["block", "blocks"],
  "palette-field": ["block", "blocks"],
};

const FIELD_TYPES: FieldType[] = [
  "text",
  "rich_text",
  "number",
  "boolean",
  "tag",
  "attachment",
];
const FIELD_TYPE_LABEL_KEYS: Record<FieldType, string> = {
  text: "fields.typeText",
  rich_text: "fields.typeRichText",
  number: "fields.typeNumber",
  boolean: "fields.typeBoolean",
  tag: "fields.typeTags",
  attachment: "fields.typeAttachment",
};
const REGION_KINDS: RegionKind[] = ["band", "columns", "tabs"];

type Selection =
  | { kind: "block"; id: string }
  | { kind: "region"; id: string }
  | { kind: "field"; index: number }
  | null;

interface TemplateDesignerProps {
  projectId: string;
  initial: EntityTemplateCreate;
  saving: boolean;
  /** Rendered inside the designer. The panel behind it also knows the error,
   * but it is covered by this modal — a rejected save (an incompatible
   * widget, a broken formula) used to look like the button did nothing. */
  error?: string | null;
  onSave: (draft: EntityTemplateCreate) => void;
  onClose: () => void;
}

/** What stops a draft from being saved, as an i18n key — a blank or duplicate
 * field key is rejected by the backend with a 422 that names neither, so the
 * designer has to catch it while the DM can still see which chip is wrong. */
function draftProblem(draft: EntityTemplateCreate): string | null {
  if (!draft.name.trim()) return "templates.problemNoName";
  if (!draft.entity_type.trim()) return "templates.problemNoType";
  if (draft.field_defs.some((f) => !f.key.trim())) return "templates.problemBlankKey";
  const keys = draft.field_defs.map((f) => f.key);
  if (new Set(keys).size !== keys.length) return "templates.problemDuplicateKey";
  return null;
}

/** Field-def indexes that carry a blank or duplicated key — highlighted in
 * the palette so "какой-то ключ не тот" points at a specific chip. */
function badFieldIndexes(fieldDefs: TemplateFieldDef[]): Set<number> {
  const bad = new Set<number>();
  const seen = new Map<string, number>();
  fieldDefs.forEach((def, i) => {
    if (!def.key.trim()) {
      bad.add(i);
      return;
    }
    const first = seen.get(def.key);
    if (first === undefined) seen.set(def.key, i);
    else {
      bad.add(first);
      bad.add(i);
    }
  });
  return bad;
}

function previewEntity(draft: EntityTemplateCreate): Entity {
  return {
    id: "preview",
    project_id: "",
    type: draft.entity_type,
    title: draft.name || "—",
    fields: draft.field_defs.map((fd) => ({
      key: fd.key,
      field_type: fd.field_type,
      value: fd.default_value ?? emptyValue(fd.field_type),
      show_on_card: fd.show_on_card,
    })),
    template_id: null,
    icon: null,
    pos_x: null,
    pos_y: null,
    revealed_to_players: false,
    player_text: null,
    created_at: "",
    updated_at: "",
  };
}

/** existing keys win — re-dropping the same preset (or two presets sharing a
 * field like `proficiency`) never duplicates a field def. */
function mergeFieldDefs(
  existing: TemplateFieldDef[],
  incoming: TemplateFieldDef[],
): TemplateFieldDef[] {
  const known = new Set(existing.map((f) => f.key));
  return [...existing, ...incoming.filter((f) => !known.has(f.key))];
}

function safeDependencies(formula: string | null | undefined): Set<string> {
  if (!formula) return new Set();
  try {
    return parseDependencies(formula);
  } catch {
    return new Set();
  }
}

function findBlock(layout: SheetLayout, blockId: string): SheetBlock | null {
  return allBlocks(layout).find((b) => b.id === blockId) ?? null;
}

function regionOfContainer(layout: SheetLayout, containerId: string): SheetRegion | null {
  return (
    layout.regions.find((r) => r.containers.some((c) => c.id === containerId)) ?? null
  );
}

/** Which block-container a drop landed in. The drop zone registers under a
 * `blocks:` prefix, never the bare container id — a band region's blocks
 * live directly under the region, and dnd-kit keys droppables by id, so
 * reusing the region's own id would silently clobber its sortable
 * droppable and break region dragging. */
function dropTargetContainer(over: DragEndEvent["over"]): string | null {
  const data = over?.data.current;
  if (data?.type === "blocks" || data?.type === "block") {
    return (data.containerId as string | undefined) ?? null;
  }
  return null;
}

/** The sibling block a drop landed on (insert before it), or null to append. */
function dropTargetBlock(over: DragEndEvent["over"]): string | null {
  return over?.data.current?.type === "block" ? String(over.id) : null;
}

export function TemplateDesigner({
  projectId,
  initial,
  saving,
  error,
  onSave,
  onClose,
}: TemplateDesignerProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<EntityTemplateCreate>(() => ({
    ...initial,
    layout: ensureIds(initial.layout),
  }));
  const [confirmingClose, setConfirmingClose] = useState(false);
  const [paletteTab, setPaletteTab] = useState<"fields" | "presets">("fields");
  const [rightTab, setRightTab] = useState<"inspector" | "preview">("inspector");
  const [selection, setSelection] = useState<Selection>(null);
  const [dragLabel, setDragLabel] = useState<string | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<{
    index: number;
    key: string;
    count: number;
  } | null>(null);
  // Keys already saved when the designer opened — their identity is locked so
  // every block/formula reference in this layout stays valid; label and type
  // remain editable, and a brand-new field's key is still free to type.
  const [lockedKeys] = useState(() => new Set(initial.field_defs.map((f) => f.key)));

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // A whole layout is many minutes of work and the backdrop covers the
  // screen — closing it on a stray click, with no warning and no way back,
  // was the single most expensive misclick in this feature.
  //
  // The baseline snapshots the draft *after* ensureIds, not `initial`:
  // opening a built-in (whose blocks carry no ids) mints an id for every one
  // of them on mount, so comparing against `initial` — or re-running
  // ensureIds, which mints different ids again — would call an untouched
  // template dirty. Lazy initializer, so it captures the first draft only.
  const [baseline] = useState(() => JSON.stringify(draft));
  const dirty = JSON.stringify(draft) !== baseline;

  const requestClose = useCallback(() => {
    if (dirty) setConfirmingClose(true);
    else onClose();
  }, [dirty, onClose]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") requestClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [requestClose]);

  const problem = draftProblem(draft);
  const badFields = useMemo(() => badFieldIndexes(draft.field_defs), [draft.field_defs]);

  const fieldType = useMemo(() => {
    const map = new Map<string, FieldType>();
    for (const fd of draft.field_defs) map.set(fd.key, fd.field_type);
    return map;
  }, [draft.field_defs]);

  function setLayout(fn: (l: SheetLayout) => SheetLayout) {
    setDraft((d) => ({ ...d, layout: fn(d.layout) }));
  }

  // --- field defs -------------------------------------------------------

  function updateFieldDef(i: number, patch: Partial<TemplateFieldDef>) {
    setDraft((d) => {
      const before = d.field_defs[i];
      const field_defs = d.field_defs.map((f, k) => (k === i ? { ...f, ...patch } : f));
      let layout = d.layout;
      if (patch.field_type && patch.field_type !== before.field_type) {
        const compatible = new Set(widgetsForFieldType(patch.field_type));
        for (const containerId of containerIds(layout)) {
          for (const block of getBlocks(layout, containerId)) {
            if (block.field_key === before.key && !compatible.has(block.widget)) {
              layout = updateBlock(layout, block.id!, {
                widget: defaultWidgetForFieldType(patch.field_type),
              });
            }
          }
        }
      }
      return { ...d, field_defs, layout };
    });
  }

  function requestRemoveField(i: number) {
    const key = draft.field_defs[i].key;
    const count = allBlocks(draft.layout).filter(
      (b) => b.field_key === key || safeDependencies(b.formula).has(key),
    ).length;
    if (count === 0) {
      setDraft((d) => ({ ...d, field_defs: d.field_defs.filter((_, k) => k !== i) }));
      setSelection(null);
      return;
    }
    setPendingRemoval({ index: i, key, count });
  }

  function confirmRemoveField() {
    if (!pendingRemoval) return;
    const { index, key } = pendingRemoval;
    setDraft((d) => ({
      ...d,
      field_defs: d.field_defs.filter((_, k) => k !== index),
      layout: removeFieldCascade(d.layout, key),
    }));
    setPendingRemoval(null);
    setSelection(null);
  }

  // --- drag and drop ----------------------------------------------------

  const collisionDetection: CollisionDetection = (args) => {
    const accepted = ACCEPTS[args.active.data.current?.type as DragType] ?? [];
    return closestCenter({
      ...args,
      droppableContainers: args.droppableContainers.filter((c) =>
        accepted.includes(c.data.current?.type as string),
      ),
    });
  };

  function handleDragStart(e: DragStartEvent) {
    setDragLabel((e.active.data.current?.label as string) ?? null);
  }

  /** Cross-container block moves happen live while hovering so the DM sees
   * the block land; region/container reorders only commit on drop. */
  function handleDragOver(e: DragOverEvent) {
    const { active, over } = e;
    if (!over || active.data.current?.type !== "block") return;
    const activeId = String(active.id);
    const to = dropTargetContainer(over);
    if (!to) return;
    setDraft((d) => {
      const from = findContainerOfBlock(d.layout, activeId);
      if (!from || from === to) return d;
      return { ...d, layout: moveBlock(d.layout, activeId, to, dropTargetBlock(over)) };
    });
  }

  function handleDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    setDragLabel(null);
    if (!over) return;
    const type = active.data.current?.type as DragType | undefined;
    const activeId = String(active.id);
    const overId = String(over.id);

    if (type === "region") {
      setDraft((d) => {
        const ids = d.layout.regions.map((r) => r.id!);
        const from = ids.indexOf(activeId);
        const to = ids.indexOf(overId);
        if (from < 0 || to < 0 || from === to) return d;
        return { ...d, layout: moveRegion(d.layout, from, to) };
      });
      return;
    }

    if (type === "container") {
      setDraft((d) => {
        const region = regionOfContainer(d.layout, activeId);
        if (!region || !region.containers.some((c) => c.id === overId)) return d;
        const ids = region.containers.map((c) => c.id!);
        const from = ids.indexOf(activeId);
        const to = ids.indexOf(overId);
        if (from < 0 || to < 0 || from === to) return d;
        return { ...d, layout: moveContainer(d.layout, region.id!, from, to) };
      });
      return;
    }

    const target = dropTargetContainer(over);
    if (!target) return;

    if (type === "palette-field") {
      const key = active.data.current?.fieldKey as string;
      setDraft((d) => {
        const ft = d.field_defs.find((f) => f.key === key)?.field_type;
        return {
          ...d,
          layout: addBlock(
            d.layout,
            target,
            ft ? defaultWidgetForFieldType(ft) : "plain",
            key,
          ),
        };
      });
      return;
    }

    setDraft((d) => {
      if (!findContainerOfBlock(d.layout, activeId)) return d;
      return {
        ...d,
        layout: moveBlock(d.layout, activeId, target, dropTargetBlock(over)),
      };
    });
  }

  const selectedBlock =
    selection?.kind === "block" ? findBlock(draft.layout, selection.id) : null;
  const selectedRegion =
    selection?.kind === "region"
      ? (draft.layout.regions.find((r) => r.id === selection.id) ?? null)
      : null;

  return (
    <div className="sheet-modal-backdrop" onClick={requestClose}>
      <div
        className="designer"
        role="dialog"
        aria-modal="true"
        aria-label={t("templates.designerTitle")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="designer-head">
          <h2>{t("templates.designerTitle")}</h2>
          <div className="designer-head-meta">
            <input
              className="designer-head-name"
              placeholder={t("templates.nameLabel")}
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            />
            <input
              className="designer-head-type"
              placeholder={t("templates.entityTypeLabel")}
              value={draft.entity_type}
              onChange={(e) => setDraft((d) => ({ ...d, entity_type: e.target.value }))}
            />
          </div>
          <div className="sheet-modal-actions">
            <button
              type="button"
              className="button-primary button-sm"
              disabled={saving || problem !== null}
              title={problem ? t(problem) : undefined}
              onClick={() => onSave(draft)}
            >
              {saving && <span className="spinner" aria-hidden="true" />}
              {t("common.save")}
            </button>
            <button
              type="button"
              className="button-sm button-ghost"
              onClick={requestClose}
            >
              {t("common.close")}
            </button>
          </div>
        </div>

        {(problem || error) && (
          <p className="designer-banner error-text" role="alert">
            {error ?? t(problem!)}
          </p>
        )}

        <DndContext
          sensors={sensors}
          collisionDetection={collisionDetection}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={() => setDragLabel(null)}
        >
          <div className="designer-body-3col">
            {/* ---------- palette ---------- */}
            <aside className="designer-palette">
              <div className="designer-palette-tabs">
                <button
                  type="button"
                  className={paletteTab === "fields" ? "seg-btn active" : "seg-btn"}
                  onClick={() => setPaletteTab("fields")}
                >
                  {t("templates.paletteFields")}
                </button>
                <button
                  type="button"
                  className={paletteTab === "presets" ? "seg-btn active" : "seg-btn"}
                  onClick={() => setPaletteTab("presets")}
                >
                  {t("templates.palettePresets")}
                </button>
              </div>

              {paletteTab === "fields" ? (
                <FieldsPalette
                  fieldDefs={draft.field_defs}
                  badFields={badFields}
                  selection={selection}
                  onSelect={(index) => setSelection({ kind: "field", index })}
                  onAdd={() => {
                    const index = draft.field_defs.length;
                    setDraft((d) => ({
                      ...d,
                      field_defs: [
                        ...d.field_defs,
                        { key: "", field_type: "text", show_on_card: false },
                      ],
                    }));
                    setSelection({ kind: "field", index });
                  }}
                />
              ) : (
                <PresetsPalette
                  projectId={projectId}
                  regions={draft.layout.regions}
                  onInsert={(regionId, containerId, preset) =>
                    setDraft((d) => ({
                      ...d,
                      field_defs: mergeFieldDefs(d.field_defs, preset.field_defs),
                      layout: insertPreset(
                        d.layout,
                        regionId,
                        containerId,
                        preset.section,
                      ),
                    }))
                  }
                />
              )}
            </aside>

            {/* ---------- canvas ---------- */}
            <div className="designer-canvas">
              <SortableContext
                items={draft.layout.regions.map((r) => r.id!)}
                strategy={verticalListSortingStrategy}
              >
                {draft.layout.regions.map((region) => (
                  <RegionCard
                    key={region.id}
                    projectId={projectId}
                    region={region}
                    fieldDefs={draft.field_defs}
                    fieldType={fieldType}
                    selection={selection}
                    onSelect={setSelection}
                    setLayout={setLayout}
                  />
                ))}
              </SortableContext>

              <div className="designer-add-region">
                <span>{t("templates.addRegion")}</span>
                <div className="designer-add-region-choices">
                  {REGION_KINDS.map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      className="button-sm"
                      onClick={() =>
                        setLayout((l) => addRegion(l, t("templates.newRegion"), kind))
                      }
                    >
                      <Icon name="plus" size={12} />
                      {t(`templates.regionKind.${kind}`)}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* ---------- inspector / preview ---------- */}
            <aside className="designer-inspector">
              <div className="designer-palette-tabs">
                <button
                  type="button"
                  className={rightTab === "inspector" ? "seg-btn active" : "seg-btn"}
                  onClick={() => setRightTab("inspector")}
                >
                  {t("templates.inspector")}
                </button>
                <button
                  type="button"
                  className={rightTab === "preview" ? "seg-btn active" : "seg-btn"}
                  onClick={() => setRightTab("preview")}
                >
                  {t("templates.preview")}
                </button>
              </div>

              {rightTab === "preview" ? (
                <SheetRenderer
                  entity={previewEntity(draft)}
                  layout={draft.layout}
                  fieldDefs={draft.field_defs}
                  mode="full"
                />
              ) : selectedBlock ? (
                <BlockInspector
                  block={selectedBlock}
                  fieldDefs={draft.field_defs}
                  fieldType={fieldType}
                  onUpdate={(patch) =>
                    setLayout((l) => updateBlock(l, selectedBlock.id!, patch))
                  }
                  onRemove={() => {
                    setLayout((l) => removeBlock(l, selectedBlock.id!));
                    setSelection(null);
                  }}
                />
              ) : selectedRegion ? (
                <RegionInspector
                  region={selectedRegion}
                  onRename={(name) =>
                    setLayout((l) => renameRegion(l, selectedRegion.id!, name))
                  }
                  onKind={(kind) =>
                    setLayout((l) => setRegionKind(l, selectedRegion.id!, kind))
                  }
                  onRemove={() => {
                    setLayout((l) => removeRegion(l, selectedRegion.id!));
                    setSelection(null);
                  }}
                />
              ) : selection?.kind === "field" && draft.field_defs[selection.index] ? (
                <FieldInspector
                  def={draft.field_defs[selection.index]}
                  locked={lockedKeys.has(draft.field_defs[selection.index].key)}
                  onUpdate={(patch) => updateFieldDef(selection.index, patch)}
                  onRemove={() => requestRemoveField(selection.index)}
                />
              ) : (
                <p className="designer-inspector-empty">
                  {t("templates.inspectorEmpty")}
                </p>
              )}
            </aside>
          </div>

          <DragOverlay dropAnimation={null}>
            {dragLabel ? <div className="designer-drag-overlay">{dragLabel}</div> : null}
          </DragOverlay>
        </DndContext>
      </div>

      {confirmingClose && (
        <ConfirmDialog
          title={t("common.leaveTitle")}
          body={t("common.leaveBody")}
          confirmLabel={t("common.leaveButton")}
          onConfirm={onClose}
          onCancel={() => setConfirmingClose(false)}
        />
      )}

      {pendingRemoval && (
        <ConfirmDialog
          title={t("templates.removeFieldTitle")}
          body={t("templates.removeFieldBody", {
            key: pendingRemoval.key,
            count: pendingRemoval.count,
          })}
          confirmLabel={t("common.remove")}
          onConfirm={confirmRemoveField}
          onCancel={() => setPendingRemoval(null)}
        />
      )}
    </div>
  );
}

// --- canvas: regions -------------------------------------------------

interface CanvasShared {
  projectId: string;
  fieldDefs: TemplateFieldDef[];
  fieldType: Map<string, FieldType>;
  selection: Selection;
  onSelect: (s: Selection) => void;
  setLayout: (fn: (l: SheetLayout) => SheetLayout) => void;
}

function RegionCard({ region, ...shared }: CanvasShared & { region: SheetRegion }) {
  const { t } = useTranslation();
  const { setLayout, selection, onSelect } = shared;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: region.id!,
      data: { type: "region", label: region.name },
    });
  const selected = selection?.kind === "region" && selection.id === region.id;

  return (
    <section
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`designer-region${isDragging ? " dragging" : ""}${
        selected ? " selected" : ""
      }`}
    >
      <header
        className="designer-region-head"
        onClick={() => onSelect({ kind: "region", id: region.id! })}
      >
        <button
          type="button"
          className="designer-grip"
          {...attributes}
          {...listeners}
          title={t("templates.drag")}
          onClick={(e) => e.stopPropagation()}
        >
          <Icon name="grip" size={14} />
        </button>
        <input
          className="designer-region-name"
          value={region.name}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => setLayout((l) => renameRegion(l, region.id!, e.target.value))}
        />
        <div className="designer-seg" onClick={(e) => e.stopPropagation()}>
          {REGION_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              className={kind === region.kind ? "seg-btn active" : "seg-btn"}
              onClick={() => setLayout((l) => setRegionKind(l, region.id!, kind))}
            >
              {t(`templates.regionKind.${kind}`)}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="icon-button icon-button-danger"
          onClick={(e) => {
            e.stopPropagation();
            setLayout((l) => removeRegion(l, region.id!));
          }}
          title={t("common.remove")}
        >
          <Icon name="trash" size={13} />
        </button>
      </header>

      {region.kind === "band" ? (
        <div className="designer-region-body">
          <BlocksDropZone containerId={region.id!} blocks={region.blocks} {...shared} />
        </div>
      ) : (
        <div className="designer-region-body">
          <SortableContext
            items={region.containers.map((c) => c.id!)}
            strategy={horizontalListSortingStrategy}
          >
            <div
              className={
                region.kind === "columns"
                  ? "designer-containers columns"
                  : "designer-containers tabs"
              }
            >
              {region.containers.map((container) => (
                <ContainerCard
                  key={container.id}
                  regionId={region.id!}
                  kind={region.kind}
                  container={container}
                  {...shared}
                />
              ))}
              <button
                type="button"
                className="designer-add-container"
                onClick={() => setLayout((l) => addContainer(l, region.id!))}
              >
                <Icon name="plus" size={13} />
                {t(region.kind === "tabs" ? "templates.addTab" : "templates.addColumn")}
              </button>
            </div>
          </SortableContext>
        </div>
      )}
    </section>
  );
}

function ContainerCard({
  regionId,
  kind,
  container,
  ...shared
}: CanvasShared & {
  regionId: string;
  kind: RegionKind;
  container: SheetContainer;
}) {
  const { t } = useTranslation();
  const { setLayout } = shared;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: container.id!,
      data: { type: "container", label: container.title ?? "" },
    });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`designer-container${isDragging ? " dragging" : ""}`}
    >
      <div className="designer-container-head">
        <button
          type="button"
          className="designer-grip"
          {...attributes}
          {...listeners}
          title={t("templates.drag")}
        >
          <Icon name="grip" size={13} />
        </button>
        <input
          placeholder={
            kind === "tabs"
              ? t("templates.tabTitlePlaceholder")
              : t("templates.columnTitlePlaceholder")
          }
          value={container.title ?? ""}
          onChange={(e) =>
            setLayout((l) => renameContainer(l, regionId, container.id!, e.target.value))
          }
        />
        <button
          type="button"
          className="icon-button icon-button-danger"
          onClick={() => setLayout((l) => removeContainer(l, regionId, container.id!))}
          title={t("common.remove")}
        >
          <Icon name="trash" size={13} />
        </button>
      </div>

      {container.sections.map((section) => (
        <SectionCard key={section.id} section={section} {...shared} />
      ))}

      <button
        type="button"
        className="designer-add-section"
        onClick={() => setLayout((l) => addSection(l, regionId, container.id!))}
      >
        <Icon name="plus" size={12} />
        {t("templates.addSection")}
      </button>
    </div>
  );
}

function SectionCard({ section, ...shared }: CanvasShared & { section: SheetSection }) {
  const { t } = useTranslation();
  const { setLayout, projectId, fieldDefs } = shared;
  const createPreset = useCreateSheetPreset(projectId);

  function saveAsPreset() {
    const used = new Set<string>();
    for (const block of section.blocks) {
      if (block.field_key) used.add(block.field_key);
      for (const dep of safeDependencies(block.formula)) used.add(dep);
    }
    const name = window.prompt(t("templates.savePresetPrompt"), section.title ?? "");
    if (!name) return;
    createPreset.mutate({
      name,
      field_defs: fieldDefs.filter((f) => used.has(f.key)),
      section: { ...section, id: undefined },
    });
  }

  return (
    <div className="designer-section">
      <div className="designer-section-head">
        <input
          placeholder={t("templates.sectionTitlePlaceholder")}
          value={section.title ?? ""}
          onChange={(e) =>
            setLayout((l) =>
              updateSection(l, section.id!, { title: e.target.value || null }),
            )
          }
        />
        <label className="designer-mini-num" title={t("templates.columns")}>
          {t("templates.columns")}
          <input
            type="number"
            min={1}
            max={4}
            value={section.columns}
            onChange={(e) =>
              setLayout((l) =>
                updateSection(l, section.id!, {
                  columns: Math.max(1, Number(e.target.value)),
                }),
              )
            }
          />
        </label>
        <button
          type="button"
          className="icon-button"
          disabled={section.blocks.length === 0 || createPreset.isPending}
          onClick={saveAsPreset}
          title={t("templates.saveAsPreset")}
        >
          <Icon name="save" size={13} />
        </button>
        <button
          type="button"
          className="icon-button icon-button-danger"
          onClick={() => setLayout((l) => removeSection(l, section.id!))}
          title={t("common.remove")}
        >
          <Icon name="trash" size={13} />
        </button>
      </div>
      <BlocksDropZone containerId={section.id!} blocks={section.blocks} {...shared} />
    </div>
  );
}

/** The one droppable that block drags (and palette-field drags) land in. */
function BlocksDropZone({
  containerId,
  blocks,
  ...shared
}: CanvasShared & { containerId: string; blocks: SheetBlock[] }) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({
    id: `blocks:${containerId}`,
    data: { type: "blocks", containerId },
  });

  return (
    <div
      ref={setNodeRef}
      className={`designer-blocks${isOver ? " over" : ""}${
        blocks.length === 0 ? " empty" : ""
      }`}
    >
      <SortableContext
        items={blocks.map((b) => b.id!)}
        strategy={verticalListSortingStrategy}
      >
        {blocks.map((block) => (
          <BlockChip
            key={block.id}
            block={block}
            containerId={containerId}
            {...shared}
          />
        ))}
      </SortableContext>
      {blocks.length === 0 && (
        <span className="designer-drop-hint">{t("templates.dropHere")}</span>
      )}
    </div>
  );
}

/** Compact chip: grip + name + widget badge. Everything else about a block
 * is edited in the inspector — cramming selects into each row is exactly
 * what made the previous designer unreadable. */
function BlockChip({
  block,
  containerId,
  fieldDefs,
  selection,
  onSelect,
}: CanvasShared & { block: SheetBlock; containerId: string }) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: block.id!,
      data: {
        type: "block",
        containerId,
        label: block.label ?? block.field_key ?? block.widget,
      },
    });
  const selected = selection?.kind === "block" && selection.id === block.id;
  const name =
    block.label ||
    fieldDefs.find((f) => f.key === block.field_key)?.label ||
    block.field_key ||
    t(WIDGET_META[block.widget].labelKey);

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`designer-block${isDragging ? " dragging" : ""}${
        selected ? " selected" : ""
      }${block.widget === "computed" ? " computed" : ""}`}
      onClick={() => onSelect({ kind: "block", id: block.id! })}
    >
      <button
        type="button"
        className="designer-grip"
        {...attributes}
        {...listeners}
        title={t("templates.drag")}
        onClick={(e) => e.stopPropagation()}
      >
        <Icon name="grip" size={13} />
      </button>
      <span className="designer-block-name">{name}</span>
      <span className="designer-block-widget">{t(WIDGET_META[block.widget].labelKey)}</span>
    </div>
  );
}

// --- palette ----------------------------------------------------------

function FieldsPalette({
  fieldDefs,
  badFields,
  selection,
  onSelect,
  onAdd,
}: {
  fieldDefs: TemplateFieldDef[];
  badFields: Set<number>;
  selection: Selection;
  onSelect: (index: number) => void;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="designer-palette-head">
        <h3>{t("templates.fields")}</h3>
        <button type="button" className="button-sm" onClick={onAdd}>
          <Icon name="plus" size={13} />
          {t("templates.addField")}
        </button>
      </div>
      <div className="designer-palette-list">
        {fieldDefs.map((def, i) => (
          <PaletteFieldChip
            key={`${def.key}-${i}`}
            def={def}
            invalid={badFields.has(i)}
            selected={selection?.kind === "field" && selection.index === i}
            onSelect={() => onSelect(i)}
          />
        ))}
      </div>
    </>
  );
}

function PaletteFieldChip({
  def,
  invalid,
  selected,
  onSelect,
}: {
  def: TemplateFieldDef;
  invalid: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `palette:${def.key}`,
    data: { type: "palette-field", fieldKey: def.key, label: def.label || def.key },
    disabled: !def.key,
  });

  return (
    <div
      ref={setNodeRef}
      className={`designer-palette-chip${isDragging ? " dragging" : ""}${
        selected ? " selected" : ""
      }${invalid ? " invalid" : ""}`}
      title={invalid ? t("templates.keyInvalid") : undefined}
      onClick={onSelect}
    >
      <button
        type="button"
        className="designer-grip"
        {...attributes}
        {...listeners}
        title={t("templates.drag")}
        onClick={(e) => e.stopPropagation()}
      >
        <Icon name="grip" size={13} />
      </button>
      <span className="designer-palette-chip-name">
        {def.label || def.key || t("fields.namePlaceholder")}
      </span>
      <span className="designer-palette-chip-type">{def.field_type}</span>
    </div>
  );
}

interface ContainerRef {
  regionId: string;
  containerId: string;
  label: string;
}

function containerRefs(regions: SheetRegion[]): ContainerRef[] {
  const refs: ContainerRef[] = [];
  for (const region of regions) {
    if (region.kind === "band") continue;
    for (const container of region.containers) {
      refs.push({
        regionId: region.id!,
        containerId: container.id!,
        label: container.title ? `${region.name} — ${container.title}` : region.name,
      });
    }
  }
  return refs;
}

function PresetsPalette({
  projectId,
  regions,
  onInsert,
}: {
  projectId: string;
  regions: SheetRegion[];
  onInsert: (regionId: string, containerId: string, preset: SheetPreset) => void;
}) {
  const { t } = useTranslation();
  const { data: presets } = useSheetPresets(projectId);
  const refs = useMemo(() => containerRefs(regions), [regions]);
  const [targetByPreset, setTargetByPreset] = useState<Record<string, string>>({});

  return (
    <>
      <div className="designer-palette-head">
        <h3>{t("templates.presetsTitle")}</h3>
      </div>
      {refs.length === 0 && (
        <p className="designer-inspector-empty">{t("templates.presetsNeedContainer")}</p>
      )}
      <div className="designer-palette-list">
        {(presets ?? []).map((preset) => {
          const targetKey = targetByPreset[preset.id] ?? refs[0]?.containerId ?? "";
          const target = refs.find((r) => r.containerId === targetKey);
          return (
            <div className="designer-preset-card" key={preset.id}>
              <div className="designer-preset-card-name">{preset.name}</div>
              <div className="designer-preset-card-actions">
                <select
                  value={targetKey}
                  disabled={refs.length === 0}
                  onChange={(e) =>
                    setTargetByPreset((prev) => ({ ...prev, [preset.id]: e.target.value }))
                  }
                >
                  {refs.map((r) => (
                    <option key={r.containerId} value={r.containerId}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="button-sm"
                  disabled={!target}
                  onClick={() =>
                    target && onInsert(target.regionId, target.containerId, preset)
                  }
                >
                  <Icon name="plus" size={13} />
                  {t("templates.insertPreset")}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// --- inspector --------------------------------------------------------

function BlockInspector({
  block,
  fieldDefs,
  fieldType,
  onUpdate,
  onRemove,
}: {
  block: SheetBlock;
  fieldDefs: TemplateFieldDef[];
  fieldType: Map<string, FieldType>;
  onUpdate: (patch: Partial<SheetBlock>) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const meta = WIDGET_META[block.widget];
  const ft = block.field_key ? fieldType.get(block.field_key) : undefined;
  // A formula-bound or decorative block keeps its widget; a field-bound one
  // may only switch to widgets that accept its field's stored type.
  const widgetOptions = meta.formulaBound
    ? WIDGET_TYPES.filter((w) => WIDGET_META[w].formulaBound)
    : meta.decorative
      ? WIDGET_TYPES.filter((w) => WIDGET_META[w].decorative)
      : ft
        ? widgetsForFieldType(ft)
        : [];

  return (
    <div className="designer-inspector-body">
      <span className="designer-inspector-tag">{t("templates.blockSelected")}</span>

      <label className="designer-field">
        {t("templates.labelPlaceholder")}
        <input
          value={block.label ?? ""}
          onChange={(e) => onUpdate({ label: e.target.value || null })}
        />
      </label>

      {widgetOptions.length > 0 && (
        <label className="designer-field">
          {t("templates.widget")}
          <select
            value={block.widget}
            onChange={(e) => onUpdate({ widget: e.target.value as WidgetType })}
          >
            {widgetOptions.map((w) => (
              <option key={w} value={w}>
                {t(WIDGET_META[w].labelKey)}
              </option>
            ))}
          </select>
        </label>
      )}

      {!meta.decorative && !meta.formulaBound && (
        <label className="designer-field">
          {t("templates.fieldBinding")}
          <select
            value={block.field_key ?? ""}
            onChange={(e) => onUpdate({ field_key: e.target.value || null })}
          >
            {/* Explicit empty option: a block with no binding yet used to
                show the first field as if it were selected, and picking that
                very field changed nothing — the sheet still rendered an
                unbound block. */}
            <option value="">{t("templates.pickField")}</option>
            {fieldDefs
              // Only fields this widget can actually draw. Offering the rest
              // just moved the failure to the save button, where the backend
              // answers 422 without naming the block.
              .filter((f) => f.key && meta.accepts.includes(f.field_type))
              .map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label || f.key}
                </option>
              ))}
          </select>
        </label>
      )}

      {block.widget === "stat_modifier" && (
        <StatModifierConfig block={block} onUpdate={onUpdate} />
      )}

      <label className="designer-field">
        {t("templates.colSpan")}
        <input
          type="number"
          min={1}
          max={4}
          value={block.colspan}
          onChange={(e) => onUpdate({ colspan: Math.max(1, Number(e.target.value)) })}
        />
      </label>

      {meta.formulaBound && (
        <FormulaEditor block={block} fieldDefs={fieldDefs} onUpdate={onUpdate} />
      )}

      <button type="button" className="button-sm button-danger" onClick={onRemove}>
        <Icon name="trash" size={13} />
        {t("common.remove")}
      </button>
    </div>
  );
}

/** The derived number next to a score is system-specific — D&D halves it,
 * other systems do something else or have no modifier at all. Exposed here so
 * a template never inherits D&D arithmetic just by using the widget. */
function StatModifierConfig({
  block,
  onUpdate,
}: {
  block: SheetBlock;
  onUpdate: (patch: Partial<SheetBlock>) => void;
}) {
  const { t } = useTranslation();
  const raw = block.config.mod_formula;
  const hidden = raw === null;
  const value = typeof raw === "string" ? raw : "";
  let error: string | null = null;
  if (value.trim()) {
    try {
      parseDependencies(value);
    } catch (e) {
      error = e instanceof FormulaSyntaxError ? e.message : String(e);
    }
  }

  function setConfig(next: unknown) {
    onUpdate({ config: { ...block.config, mod_formula: next } });
  }

  return (
    <div className="designer-formula-box">
      <label className="designer-toggleable-item">
        <input
          type="checkbox"
          checked={!hidden}
          onChange={(e) => setConfig(e.target.checked ? "" : null)}
        />
        {t("templates.showModifier")}
      </label>
      {!hidden && (
        <>
          <label className="designer-field">
            {t("templates.modFormula")}
            <input
              value={value}
              placeholder={DEFAULT_STAT_MOD_FORMULA}
              onChange={(e) => setConfig(e.target.value)}
            />
          </label>
          {error ? (
            <span className="designer-formula-error">{error}</span>
          ) : (
            <span className="field-hint">{t("templates.modFormulaHint")}</span>
          )}
        </>
      )}
    </div>
  );
}

function FormulaEditor({
  block,
  fieldDefs,
  onUpdate,
}: {
  block: SheetBlock;
  fieldDefs: TemplateFieldDef[];
  onUpdate: (patch: Partial<SheetBlock>) => void;
}) {
  const { t } = useTranslation();
  const knownKeys = useMemo(() => new Set(fieldDefs.map((f) => f.key)), [fieldDefs]);
  const booleanKeys = useMemo(
    () => fieldDefs.filter((f) => f.field_type === "boolean").map((f) => f.key),
    [fieldDefs],
  );
  let deps: Set<string> = new Set();
  let error: string | null = null;
  try {
    deps = block.formula ? parseDependencies(block.formula) : new Set();
  } catch (e) {
    error = e instanceof FormulaSyntaxError ? e.message : String(e);
  }
  const toggleable = new Set(
    Array.isArray(block.config.toggleable) ? (block.config.toggleable as string[]) : [],
  );
  const availableToggles = booleanKeys.filter((k) => deps.has(k));

  return (
    <div className="designer-formula-box">
      <label className="designer-field">
        {t("widgets.computed")}
        <textarea
          className="designer-formula"
          placeholder={t("templates.formulaPlaceholder")}
          value={block.formula ?? ""}
          onChange={(e) => onUpdate({ formula: e.target.value })}
          rows={3}
        />
      </label>
      {error ? (
        <span className="designer-formula-error">{error}</span>
      ) : (
        deps.size > 0 && (
          <div className="designer-formula-deps">
            {[...deps].map((key) => (
              <span
                key={key}
                className={
                  knownKeys.has(key) ? "designer-dep-chip ok" : "designer-dep-chip bad"
                }
              >
                {key}
              </span>
            ))}
          </div>
        )
      )}
      {/* "+3" means "add this to a roll"; a passive score or a total does not
          get a sign. Per-block, because both live on the same sheet. */}
      <label className="designer-toggleable-item">
        <input
          type="checkbox"
          checked={block.config.signed === true}
          onChange={(e) =>
            onUpdate({ config: { ...block.config, signed: e.target.checked } })
          }
        />
        {t("templates.signedValue")}
      </label>
      {availableToggles.length > 0 && (
        <div className="designer-toggleable">
          <span className="designer-toggleable-label">{t("templates.toggleable")}</span>
          {availableToggles.map((key) => (
            <label key={key} className="designer-toggleable-item">
              <input
                type="checkbox"
                checked={toggleable.has(key)}
                onChange={(e) => {
                  const next = new Set(toggleable);
                  if (e.target.checked) next.add(key);
                  else next.delete(key);
                  onUpdate({ config: { ...block.config, toggleable: [...next] } });
                }}
              />
              {key}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function RegionInspector({
  region,
  onRename,
  onKind,
  onRemove,
}: {
  region: SheetRegion;
  onRename: (name: string) => void;
  onKind: (kind: RegionKind) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="designer-inspector-body">
      <span className="designer-inspector-tag region">
        {t("templates.regionSelected")}
      </span>
      <label className="designer-field">
        {t("templates.nameLabel")}
        <input value={region.name} onChange={(e) => onRename(e.target.value)} />
      </label>
      <label className="designer-field">
        {t("templates.regionKindLabel")}
        <select
          value={region.kind}
          onChange={(e) => onKind(e.target.value as RegionKind)}
        >
          {REGION_KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {t(`templates.regionKind.${kind}`)}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="button-sm button-danger" onClick={onRemove}>
        <Icon name="trash" size={13} />
        {t("common.remove")}
      </button>
    </div>
  );
}

function FieldInspector({
  def,
  locked,
  onUpdate,
  onRemove,
}: {
  def: TemplateFieldDef;
  locked: boolean;
  onUpdate: (patch: Partial<TemplateFieldDef>) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="designer-inspector-body">
      <span className="designer-inspector-tag field">{t("templates.fieldSelected")}</span>
      <label className="designer-field">
        {t("fields.namePlaceholder")}
        <input
          value={def.key}
          readOnly={locked}
          title={locked ? t("templates.keyLocked") : undefined}
          onChange={(e) => onUpdate({ key: e.target.value })}
        />
      </label>
      <label className="designer-field">
        {t("entityEdit.typeLabel")}
        <select
          value={def.field_type}
          onChange={(e) => onUpdate({ field_type: e.target.value as FieldType })}
        >
          {FIELD_TYPES.map((ft) => (
            <option key={ft} value={ft}>
              {t(FIELD_TYPE_LABEL_KEYS[ft])}
            </option>
          ))}
        </select>
      </label>
      <label className="designer-field">
        {t("templates.labelPlaceholder")}
        <input
          value={def.label ?? ""}
          onChange={(e) => onUpdate({ label: e.target.value || null })}
        />
      </label>
      <button type="button" className="button-sm button-danger" onClick={onRemove}>
        <Icon name="trash" size={13} />
        {t("common.remove")}
      </button>
    </div>
  );
}
