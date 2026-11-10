/*
  Turning the flat entity graph into a folder tree for the list view.

  The graph itself stays flat (any entity can link to any other) — this module
  only *reads* it and picks the subset of edge types that mean containment, so
  "Безглазые --contains--> Аранис" can be shown as a folder with a member
  inside. Nothing here mutates the graph, and an entity that happens to sit in
  two folders is shown in both rather than being forced into one home.

  Pure functions on purpose: the interesting cases (an entity with several
  parents, a cycle a DM drew by accident, an inverse edge type) are all
  testable without React — see hierarchy.test.ts.
*/

import type { Edge, Entity } from "../api/types";

/** Which edge types build the tree, and which way they point.
 *
 * `forward`: the edge source is the folder — `faction --contains--> npc`.
 * `inverse`: the edge source is the member — `npc --member_of--> faction`.
 *
 * Both directions exist in real projects: the agent writes `member_of` and
 * `located_in` (see backend prompts), while the graph UI suggests `contains`. */
export interface HierarchyConfig {
  forward: string[];
  inverse: string[];
}

/* Strictly "is inside / is part of". Possession (`owns`, `rules`) is left out
 * on purpose: it would nest a whole town under the NPC who runs its smithy,
 * which is a relationship the graph shows better than a folder does. A DM who
 * wants it can add the type in the project settings. */
export const DEFAULT_HIERARCHY: HierarchyConfig = {
  forward: ["contains"],
  inverse: ["member_of", "located_in", "part_of", "belongs_to"],
};

/** A DM can nest deeply, but a runaway chain (or a cycle we somehow missed)
 * must not build an unbounded tree. */
const MAX_DEPTH = 12;

export interface HierarchyIndex {
  /** parent id → ids of its members, unordered. */
  childrenOf: Map<string, string[]>;
  /** child id → ids of every folder holding it (more than one is legal). */
  parentsOf: Map<string, string[]>;
  /** Whether any edge at all matched the config — false means "this project
   * has no containment yet", and the list should not offer grouping. */
  hasAny: boolean;
}

export interface TreeNode {
  entity: Entity;
  /** Ids from the root down to this node. Identifies a *position* rather than
   * an entity, so an entity in two folders keeps two independent expand
   * states, and it doubles as a stable React key. */
  path: string[];
  children: TreeNode[];
  /** How many folders hold this entity overall (> 1 → it is shown more than
   * once, and the row says so). */
  parentCount: number;
}

function normalize(type: string): string {
  return type.trim().toLowerCase();
}

function push(map: Map<string, string[]>, key: string, value: string): void {
  const existing = map.get(key);
  if (existing) {
    if (!existing.includes(value)) existing.push(value);
  } else {
    map.set(key, [value]);
  }
}

/** Index the containment edges of a project. O(edges). */
export function buildHierarchy(
  edges: Edge[],
  config: HierarchyConfig = DEFAULT_HIERARCHY,
): HierarchyIndex {
  const forward = new Set(config.forward.map(normalize));
  const inverse = new Set(config.inverse.map(normalize));
  const childrenOf = new Map<string, string[]>();
  const parentsOf = new Map<string, string[]>();
  let hasAny = false;

  for (const edge of edges) {
    const type = normalize(edge.type);
    const isForward = forward.has(type);
    if (!isForward && !inverse.has(type)) continue;
    const parent = isForward ? edge.source_entity_id : edge.target_entity_id;
    const child = isForward ? edge.target_entity_id : edge.source_entity_id;
    // A self-link is a data error, not a folder that contains itself.
    if (parent === child) continue;
    push(childrenOf, parent, child);
    push(parentsOf, child, parent);
    hasAny = true;
  }

  return { childrenOf, parentsOf, hasAny };
}

/** Build the visible forest: roots first, members nested underneath.
 *
 * Sibling order follows the order of `entities`, so the tree inherits whatever
 * ordering the list already had instead of inventing its own. */
export function buildForest(
  entities: Entity[],
  index: HierarchyIndex,
): TreeNode[] {
  const byId = new Map(entities.map((entity) => [entity.id, entity]));
  const rank = new Map(entities.map((entity, i) => [entity.id, i]));

  const parentsPresent = (id: string): string[] =>
    (index.parentsOf.get(id) ?? []).filter((parentId) => byId.has(parentId));

  const build = (entity: Entity, path: string[]): TreeNode => {
    const nextPath = [...path, entity.id];
    const childIds =
      nextPath.length > MAX_DEPTH ? [] : (index.childrenOf.get(entity.id) ?? []);
    const children = childIds
      .filter((id) => byId.has(id) && !path.includes(id) && id !== entity.id)
      .sort((a, b) => (rank.get(a) ?? 0) - (rank.get(b) ?? 0))
      .map((id) => build(byId.get(id)!, nextPath));
    return {
      entity,
      path: nextPath,
      children,
      parentCount: parentsPresent(entity.id).length,
    };
  };

  // A root is an entity nobody holds. Two entities that hold each other are a
  // cycle with no root at all — the first of them (by list order) is promoted
  // so its branch stays reachable instead of vanishing from the list.
  const placed = new Set<string>();
  const roots: TreeNode[] = [];
  const addRoot = (entity: Entity) => {
    const node = build(entity, []);
    roots.push(node);
    const mark = (n: TreeNode) => {
      placed.add(n.entity.id);
      n.children.forEach(mark);
    };
    mark(node);
  };

  for (const entity of entities) {
    if (parentsPresent(entity.id).length === 0) addRoot(entity);
  }
  for (const entity of entities) {
    if (!placed.has(entity.id)) addRoot(entity);
  }

  return roots;
}

export interface FilteredNode {
  entity: Entity;
  path: string[];
  children: FilteredNode[];
  parentCount: number;
  /** False = this row is only here as the way to a matching member; it is
   * dimmed rather than dropped, because hiding a folder would hide its hit. */
  matches: boolean;
}

/** Keep every node that matches, plus the folders leading to it. */
export function filterForest(
  nodes: TreeNode[],
  predicate: (entity: Entity) => boolean,
): FilteredNode[] {
  const walk = (node: TreeNode): FilteredNode | null => {
    const children = node.children
      .map(walk)
      .filter((child): child is FilteredNode => child !== null);
    const matches = predicate(node.entity);
    if (!matches && children.length === 0) return null;
    return {
      entity: node.entity,
      path: node.path,
      children,
      parentCount: node.parentCount,
      matches,
    };
  };
  return nodes
    .map(walk)
    .filter((node): node is FilteredNode => node !== null);
}

/** Every folder position in a forest — what "expand all" has to switch on. */
export function folderKeys(nodes: FilteredNode[]): string[] {
  const keys: string[] = [];
  const walk = (node: FilteredNode) => {
    if (node.children.length > 0) {
      keys.push(pathKey(node.path));
      node.children.forEach(walk);
    }
  };
  nodes.forEach(walk);
  return keys;
}

/** Stable identifier of a position in the tree (expand state, React key). */
export function pathKey(path: string[]): string {
  return path.join("/");
}

export interface HierarchyVisibility {
  visibleIds: Set<string>;
  /** Collapsed id → how many of its hierarchy descendants ended up hidden as
   * a result (i.e. not reachable through any other open path either). Omits
   * ids that hide nothing, so a "+N" badge can just check `.get(id)`. */
  hiddenDescendantCount: Map<string, number>;
}

/** Which entities are on screen, given which ids the graph view has
 * collapsed.
 *
 * Reuses `buildForest` rather than walking `childrenOf` directly: the forest
 * already has one node per (entity, position) pair, so an entity with two
 * parents shows up as two independent branches (see the "two folders" case
 * in buildForest's own tests). Walking it top-down and tracking "is a
 * collapsed id somewhere above me on *this* path" gets multi-parent
 * semantics for free — an entity is visible the moment any one of its
 * positions reaches it without crossing a collapsed ancestor, exactly the
 * "union of open paths" rule the graph view needs. Collapsing a node never
 * hides the node itself, only what's under it. */
export function computeHierarchyVisibility(
  entities: Entity[],
  index: HierarchyIndex,
  collapsedIds: ReadonlySet<string>,
): HierarchyVisibility {
  const forest = buildForest(entities, index);
  const visibleIds = new Set<string>();

  const walk = (node: TreeNode, hiddenByAncestor: boolean) => {
    if (!hiddenByAncestor) visibleIds.add(node.entity.id);
    const hiddenBelow = hiddenByAncestor || collapsedIds.has(node.entity.id);
    node.children.forEach((child) => walk(child, hiddenBelow));
  };
  forest.forEach((root) => walk(root, false));

  const hiddenDescendantCount = new Map<string, number>();
  for (const id of collapsedIds) {
    const hidden = countHiddenDescendants(index, id, visibleIds);
    if (hidden > 0) hiddenDescendantCount.set(id, hidden);
  }

  return { visibleIds, hiddenDescendantCount };
}

/** `id`'s hierarchy descendants — its own `childrenOf`, transitively, which
 * is the same flat parent→child graph regardless of which of `id`'s own
 * positions this count is attached to — that are not visible through any
 * path at all. Same depth/cycle guard as `buildForest`. */
function countHiddenDescendants(
  index: HierarchyIndex,
  id: string,
  visibleIds: ReadonlySet<string>,
): number {
  const seen = new Set<string>();
  const queue: { id: string; depth: number }[] = [{ id, depth: 0 }];
  let hidden = 0;
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current.depth >= MAX_DEPTH) continue;
    for (const child of index.childrenOf.get(current.id) ?? []) {
      if (seen.has(child) || child === id) continue;
      seen.add(child);
      if (!visibleIds.has(child)) hidden++;
      queue.push({ id: child, depth: current.depth + 1 });
    }
  }
  return hidden;
}

/** Ordinary graph edges with both ends on screen — an edge touching a node
 * hidden by a collapsed branch has nowhere to draw itself. */
export function filterVisibleEdges(edges: Edge[], visibleIds: ReadonlySet<string>): Edge[] {
  return edges.filter(
    (edge) => visibleIds.has(edge.source_entity_id) && visibleIds.has(edge.target_entity_id),
  );
}

/** Would linking `childId` under `parentId` create a loop? Used by drag and
 * drop, which is the only place in the UI that can create such an edge. */
export function wouldCycle(
  index: HierarchyIndex,
  parentId: string,
  childId: string,
): boolean {
  if (parentId === childId) return true;
  const seen = new Set<string>([childId]);
  const queue = [childId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const descendant of index.childrenOf.get(current) ?? []) {
      if (descendant === parentId) return true;
      if (!seen.has(descendant)) {
        seen.add(descendant);
        queue.push(descendant);
      }
    }
  }
  return false;
}
