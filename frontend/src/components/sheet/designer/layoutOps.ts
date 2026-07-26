import type {
  RegionKind,
  SheetBlock,
  SheetContainer,
  SheetLayout,
  SheetRegion,
  SheetSection,
  WidgetType,
} from "../../../api/types";
import { parseDependencies } from "../widgets/formula";

/** Pure, id-keyed operations on a sheet layout. Kept side-effect-free so the
 * drag-and-drop designer stays predictable (and unit-testable later).
 *
 * A "block container" is either a band region itself (its `id`) or a
 * section nested inside a columns/tabs region's container (its `id`) — both
 * are just "the place blocks live", and moveBlock/findContainerOfBlock etc.
 * don't care which one they're looking at. */

let counter = 0;
function newId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${counter++}`;
  return `${prefix}_${rand}`;
}

function emptySection(title: string | null): SheetSection {
  return { id: newId("sec"), title, columns: 1, blocks: [] };
}

function emptyContainer(title: string | null): SheetContainer {
  return { id: newId("cnt"), title, sections: [emptySection(null)] };
}

/** Assign stable ids to every region/container/section/block that lacks one
 * (on load — hand-authored builtins have none). */
export function ensureIds(layout: SheetLayout): SheetLayout {
  const block = (b: SheetBlock): SheetBlock => ({ ...b, id: b.id ?? newId("blk") });
  const section = (s: SheetSection): SheetSection => ({
    ...s,
    id: s.id ?? newId("sec"),
    blocks: s.blocks.map(block),
  });
  const container = (c: SheetContainer): SheetContainer => ({
    ...c,
    id: c.id ?? newId("cnt"),
    sections: c.sections.map(section),
  });
  return {
    regions: layout.regions.map((r) => ({
      ...r,
      id: r.id ?? newId("rgn"),
      blocks: r.blocks.map(block),
      containers: r.containers.map(container),
    })),
  };
}

/** Every block container: every band region, plus every section inside
 * every columns/tabs region's containers. */
export function containerIds(layout: SheetLayout): string[] {
  const ids: string[] = [];
  for (const region of layout.regions) {
    if (region.kind === "band") {
      ids.push(region.id!);
    } else {
      for (const container of region.containers) {
        for (const section of container.sections) ids.push(section.id!);
      }
    }
  }
  return ids;
}

export function getBlocks(layout: SheetLayout, containerId: string): SheetBlock[] {
  for (const region of layout.regions) {
    if (region.kind === "band") {
      if (region.id === containerId) return region.blocks;
      continue;
    }
    for (const container of region.containers) {
      for (const section of container.sections) {
        if (section.id === containerId) return section.blocks;
      }
    }
  }
  return [];
}

function setBlocks(
  layout: SheetLayout,
  containerId: string,
  blocks: SheetBlock[],
): SheetLayout {
  return {
    regions: layout.regions.map((region) => {
      if (region.kind === "band") {
        return region.id === containerId ? { ...region, blocks } : region;
      }
      return {
        ...region,
        containers: region.containers.map((container) => ({
          ...container,
          sections: container.sections.map((section) =>
            section.id === containerId ? { ...section, blocks } : section,
          ),
        })),
      };
    }),
  };
}

/** Every block in the layout, regardless of region/container/section.
 *
 * Walks the structure rather than going through `containerIds`: those ids
 * only exist after `ensureIds`, which the designer runs but the renderer
 * does not. On a builtin layout (no ids at all) the id-keyed route matched
 * `undefined === undefined` on the first band region and reported its six
 * blocks as the whole sheet — so the renderer thought every other field was
 * unplaced and dumped the entire entity into "Other fields".
 * Mirrors SheetLayout.all_blocks() on the backend. */
export function allBlocks(layout: SheetLayout): SheetBlock[] {
  const blocks: SheetBlock[] = [];
  for (const region of layout.regions) {
    blocks.push(...region.blocks);
    for (const container of region.containers) {
      for (const section of container.sections) blocks.push(...section.blocks);
    }
  }
  return blocks;
}

export function findContainerOfBlock(
  layout: SheetLayout,
  blockId: string,
): string | null {
  for (const id of containerIds(layout)) {
    if (getBlocks(layout, id).some((b) => b.id === blockId)) return id;
  }
  return null;
}

/** Resolve a droppable id (either a container id or a block id) to its
 * container. Lets drops land on empty containers or on a sibling block. */
export function resolveContainer(layout: SheetLayout, id: string): string | null {
  if (containerIds(layout).includes(id)) return id;
  return findContainerOfBlock(layout, id);
}

/** Move a block next to `overId` (a block) or to the end of `overContainerId`. */
export function moveBlock(
  layout: SheetLayout,
  activeId: string,
  overContainerId: string,
  overId: string | null,
): SheetLayout {
  const from = findContainerOfBlock(layout, activeId);
  if (from === null) return layout;
  const fromBlocks = getBlocks(layout, from);
  const block = fromBlocks.find((b) => b.id === activeId);
  if (!block) return layout;

  let next = setBlocks(
    layout,
    from,
    fromBlocks.filter((b) => b.id !== activeId),
  );
  const toBlocks = getBlocks(next, overContainerId);
  const overIndex =
    overId && overId !== activeId ? toBlocks.findIndex((b) => b.id === overId) : -1;
  const idx = overIndex < 0 ? toBlocks.length : overIndex;
  next = setBlocks(next, overContainerId, [
    ...toBlocks.slice(0, idx),
    block,
    ...toBlocks.slice(idx),
  ]);
  return next;
}

export function updateBlock(
  layout: SheetLayout,
  blockId: string,
  patch: Partial<SheetBlock>,
): SheetLayout {
  const container = findContainerOfBlock(layout, blockId);
  if (container === null) return layout;
  return setBlocks(
    layout,
    container,
    getBlocks(layout, container).map((b) =>
      b.id === blockId ? { ...b, ...patch } : b,
    ),
  );
}

export function removeBlock(layout: SheetLayout, blockId: string): SheetLayout {
  const container = findContainerOfBlock(layout, blockId);
  if (container === null) return layout;
  return setBlocks(
    layout,
    container,
    getBlocks(layout, container).filter((b) => b.id !== blockId),
  );
}

export function addBlock(
  layout: SheetLayout,
  containerId: string,
  widget: WidgetType,
  fieldKey: string | null,
): SheetLayout {
  const block: SheetBlock = {
    id: newId("blk"),
    widget,
    field_key: fieldKey,
    formula: null,
    label: null,
    colspan: 1,
    config: {},
  };
  return setBlocks(layout, containerId, [...getBlocks(layout, containerId), block]);
}

/** Remove every block that references `fieldKey` — either directly
 * (field_key) or through a COMPUTED formula's dependencies — used when a
 * field def is deleted from the designer's field editor so the layout never
 * ends up with a dangling reference (see TemplateDesigner's field cascade). */
export function removeFieldCascade(layout: SheetLayout, fieldKey: string): SheetLayout {
  let next = layout;
  for (const containerId of containerIds(layout)) {
    const blocks = getBlocks(next, containerId);
    const kept = blocks.filter((block) => {
      if (block.field_key === fieldKey) return false;
      if (block.widget === "computed" && block.formula) {
        try {
          if (parseDependencies(block.formula).has(fieldKey)) return false;
        } catch {
          // Malformed formula mid-edit — leave it for the widget/formula
          // inspector to flag, cascade-delete is not the place to surface it.
        }
      }
      return true;
    });
    if (kept.length !== blocks.length) next = setBlocks(next, containerId, kept);
  }
  return next;
}

// --- regions ---------------------------------------------------------------

export function addRegion(layout: SheetLayout, name: string, kind: RegionKind): SheetLayout {
  const region: SheetRegion = {
    id: newId("rgn"),
    name,
    kind,
    blocks: [],
    containers: kind === "band" ? [] : [emptyContainer(null)],
  };
  return { regions: [...layout.regions, region] };
}

export function removeRegion(layout: SheetLayout, regionId: string): SheetLayout {
  return { regions: layout.regions.filter((r) => r.id !== regionId) };
}

export function renameRegion(
  layout: SheetLayout,
  regionId: string,
  name: string,
): SheetLayout {
  return {
    regions: layout.regions.map((r) => (r.id === regionId ? { ...r, name } : r)),
  };
}

export function moveRegion(
  layout: SheetLayout,
  fromIndex: number,
  toIndex: number,
): SheetLayout {
  const regions = [...layout.regions];
  const [moved] = regions.splice(fromIndex, 1);
  regions.splice(toIndex, 0, moved);
  return { regions };
}

/** Convert a region between band/columns/tabs, reshaping its content rather
 * than discarding it: band -> columns|tabs wraps the flat blocks into one
 * section in one container; columns|tabs -> band flattens every block back
 * into a single list. columns <-> tabs keeps containers as-is (only the
 * kind, which purely affects rendering, changes). */
export function setRegionKind(
  layout: SheetLayout,
  regionId: string,
  kind: RegionKind,
): SheetLayout {
  return {
    regions: layout.regions.map((region) => {
      if (region.id !== regionId || region.kind === kind) return region;
      if (kind === "band") {
        const blocks = region.containers.flatMap((c) =>
          c.sections.flatMap((s) => s.blocks),
        );
        return { ...region, kind, blocks, containers: [] };
      }
      if (region.kind === "band") {
        const container: SheetContainer = {
          id: newId("cnt"),
          title: null,
          sections: [{ ...emptySection(null), blocks: region.blocks }],
        };
        return { ...region, kind, blocks: [], containers: [container] };
      }
      return { ...region, kind };
    }),
  };
}

// --- containers (columns/tabs) ---------------------------------------------

export function addContainer(layout: SheetLayout, regionId: string): SheetLayout {
  return {
    regions: layout.regions.map((r) =>
      r.id === regionId
        ? { ...r, containers: [...r.containers, emptyContainer(null)] }
        : r,
    ),
  };
}

export function removeContainer(
  layout: SheetLayout,
  regionId: string,
  containerId: string,
): SheetLayout {
  return {
    regions: layout.regions.map((r) =>
      r.id === regionId
        ? { ...r, containers: r.containers.filter((c) => c.id !== containerId) }
        : r,
    ),
  };
}

export function renameContainer(
  layout: SheetLayout,
  regionId: string,
  containerId: string,
  title: string,
): SheetLayout {
  return {
    regions: layout.regions.map((r) =>
      r.id === regionId
        ? {
            ...r,
            containers: r.containers.map((c) =>
              c.id === containerId ? { ...c, title } : c,
            ),
          }
        : r,
    ),
  };
}

export function moveContainer(
  layout: SheetLayout,
  regionId: string,
  fromIndex: number,
  toIndex: number,
): SheetLayout {
  return {
    regions: layout.regions.map((r) => {
      if (r.id !== regionId) return r;
      const containers = [...r.containers];
      const [moved] = containers.splice(fromIndex, 1);
      containers.splice(toIndex, 0, moved);
      return { ...r, containers };
    }),
  };
}

// --- sections ----------------------------------------------------------

export function addSection(
  layout: SheetLayout,
  regionId: string,
  containerId: string,
): SheetLayout {
  return {
    regions: layout.regions.map((r) =>
      r.id === regionId
        ? {
            ...r,
            containers: r.containers.map((c) =>
              c.id === containerId
                ? { ...c, sections: [...c.sections, emptySection(null)] }
                : c,
            ),
          }
        : r,
    ),
  };
}

export function updateSection(
  layout: SheetLayout,
  sectionId: string,
  patch: Partial<SheetSection>,
): SheetLayout {
  const apply = (s: SheetSection) => (s.id === sectionId ? { ...s, ...patch } : s);
  return {
    regions: layout.regions.map((r) => ({
      ...r,
      containers: r.containers.map((c) => ({ ...c, sections: c.sections.map(apply) })),
    })),
  };
}

export function removeSection(layout: SheetLayout, sectionId: string): SheetLayout {
  return {
    regions: layout.regions.map((r) => ({
      ...r,
      containers: r.containers.map((c) => ({
        ...c,
        sections: c.sections.filter((s) => s.id !== sectionId),
      })),
    })),
  };
}

/** Drop a preset's section into `containerId` — a deep clone with fresh ids
 * so re-dropping the same preset twice never collides. Merging the preset's
 * field_defs into the template's own is a separate, template-level concern
 * (see TemplateDesigner's mergeFieldDefs) — layoutOps only ever touches the
 * layout, never field_defs. */
export function insertPreset(
  layout: SheetLayout,
  regionId: string,
  containerId: string,
  section: SheetSection,
): SheetLayout {
  const cloned: SheetSection = {
    ...section,
    id: newId("sec"),
    blocks: section.blocks.map((b) => ({ ...b, id: newId("blk") })),
  };
  return {
    regions: layout.regions.map((r) =>
      r.id === regionId
        ? {
            ...r,
            containers: r.containers.map((c) =>
              c.id === containerId ? { ...c, sections: [...c.sections, cloned] } : c,
            ),
          }
        : r,
    ),
  };
}
