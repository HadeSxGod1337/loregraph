import { describe, expect, it } from "vitest";

import type { Edge, Entity } from "../api/types";
import {
  buildForest,
  buildHierarchy,
  computeHierarchyVisibility,
  filterForest,
  filterVisibleEdges,
  folderKeys,
  wouldCycle,
} from "./hierarchy";

function entity(id: string, title = id): Entity {
  return {
    id,
    project_id: "p1",
    type: "npc",
    title,
    fields: [],
    template_id: null,
    icon: null,
    pos_x: null,
    pos_y: null,
    revealed_to_players: false,
    player_text: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function edge(source: string, target: string, type: string): Edge {
  return {
    id: `${source}-${type}-${target}`,
    project_id: "p1",
    source_entity_id: source,
    target_entity_id: target,
    type,
    label: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

/** Titles of a forest, nested — compact enough to assert on directly. */
function shape(nodes: { entity: Entity; children: unknown[] }[]): unknown[] {
  return nodes.map((node) => [
    node.entity.title,
    shape(node.children as { entity: Entity; children: unknown[] }[]),
  ]);
}

describe("buildHierarchy", () => {
  it("reads forward and inverse edge types into the same direction", () => {
    const index = buildHierarchy([
      edge("faction", "npc_a", "contains"),
      edge("npc_b", "faction", "member_of"),
    ]);
    expect(index.childrenOf.get("faction")).toEqual(["npc_a", "npc_b"]);
    expect(index.parentsOf.get("npc_b")).toEqual(["faction"]);
    expect(index.hasAny).toBe(true);
  });

  it("ignores edge types that are not containment", () => {
    const index = buildHierarchy([edge("npc_a", "npc_b", "ally_of")]);
    expect(index.hasAny).toBe(false);
    expect(index.childrenOf.size).toBe(0);
  });

  it("ignores an entity linked to itself", () => {
    const index = buildHierarchy([edge("npc_a", "npc_a", "contains")]);
    expect(index.hasAny).toBe(false);
  });
});

describe("buildForest", () => {
  it("nests members under their folder and keeps loose entities as roots", () => {
    const entities = [entity("faction"), entity("npc_a"), entity("item")];
    const index = buildHierarchy([edge("faction", "npc_a", "contains")]);
    expect(shape(buildForest(entities, index))).toEqual([
      ["faction", [["npc_a", []]]],
      ["item", []],
    ]);
  });

  it("shows an entity with two folders in both of them", () => {
    const entities = [entity("guild"), entity("watch"), entity("npc_a")];
    const index = buildHierarchy([
      edge("guild", "npc_a", "contains"),
      edge("npc_a", "watch", "member_of"),
    ]);
    const forest = buildForest(entities, index);
    expect(shape(forest)).toEqual([
      ["guild", [["npc_a", []]]],
      ["watch", [["npc_a", []]]],
    ]);
    expect(forest[0].children[0].parentCount).toBe(2);
    // Two positions, two independent expand states.
    expect(forest[0].children[0].path).toEqual(["guild", "npc_a"]);
    expect(forest[1].children[0].path).toEqual(["watch", "npc_a"]);
  });

  it("keeps nesting depth beyond one level", () => {
    const entities = [entity("region"), entity("town"), entity("tavern")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    expect(shape(buildForest(entities, index))).toEqual([
      ["region", [["town", [["tavern", []]]]]],
    ]);
  });

  it("survives a cycle instead of recursing forever", () => {
    const entities = [entity("a"), entity("b")];
    const index = buildHierarchy([
      edge("a", "b", "contains"),
      edge("b", "a", "contains"),
    ]);
    // Nobody is parentless, so the first entity is promoted to a root and the
    // branch stops where it would repeat itself.
    expect(shape(buildForest(entities, index))).toEqual([
      ["a", [["b", []]]],
    ]);
  });

  it("ignores edges pointing at entities outside the list", () => {
    const entities = [entity("npc_a")];
    const index = buildHierarchy([edge("deleted_faction", "npc_a", "contains")]);
    expect(shape(buildForest(entities, index))).toEqual([["npc_a", []]]);
  });
});

describe("filterForest", () => {
  const entities = [entity("faction"), entity("npc_a"), entity("npc_b")];
  const index = buildHierarchy([
    edge("faction", "npc_a", "contains"),
    edge("faction", "npc_b", "contains"),
  ]);

  it("keeps the folder of a matching member as context", () => {
    const filtered = filterForest(
      buildForest(entities, index),
      (e) => e.title === "npc_b",
    );
    expect(shape(filtered)).toEqual([["faction", [["npc_b", []]]]]);
    expect(filtered[0].matches).toBe(false);
    expect(filtered[0].children[0].matches).toBe(true);
  });

  it("keeps a matching folder even when no member matches", () => {
    const filtered = filterForest(
      buildForest(entities, index),
      (e) => e.title === "faction",
    );
    expect(shape(filtered)).toEqual([["faction", []]]);
  });

  it("drops branches with nothing in them", () => {
    const filtered = filterForest(buildForest(entities, index), () => false);
    expect(filtered).toEqual([]);
  });
});

describe("folderKeys", () => {
  it("lists every position that has members", () => {
    const entities = [entity("region"), entity("town"), entity("tavern")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    const forest = filterForest(buildForest(entities, index), () => true);
    expect(folderKeys(forest)).toEqual(["region", "region/town"]);
  });
});

describe("computeHierarchyVisibility", () => {
  it("shows a plain parent and child when nothing is collapsed", () => {
    const entities = [entity("faction"), entity("npc_a")];
    const index = buildHierarchy([edge("faction", "npc_a", "contains")]);
    const { visibleIds } = computeHierarchyVisibility(entities, index, new Set());
    expect(visibleIds).toEqual(new Set(["faction", "npc_a"]));
  });

  it("shows every node down a deep branch when nothing is collapsed", () => {
    const entities = [entity("region"), entity("town"), entity("tavern")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    const { visibleIds } = computeHierarchyVisibility(entities, index, new Set());
    expect(visibleIds).toEqual(new Set(["region", "town", "tavern"]));
  });

  it("collapsing a parent hides its descendants, transitively", () => {
    const entities = [entity("region"), entity("town"), entity("tavern")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    const { visibleIds, hiddenDescendantCount } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["region"]),
    );
    expect(visibleIds).toEqual(new Set(["region"]));
    expect(hiddenDescendantCount.get("region")).toBe(2);
  });

  it("expanding again shows the descendants once more", () => {
    const entities = [entity("region"), entity("town"), entity("tavern")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    // Same data as the collapse case above, minus "region" from the set —
    // exactly what toggling the chevron back open does to collapsedIds.
    const { visibleIds } = computeHierarchyVisibility(entities, index, new Set());
    expect(visibleIds).toEqual(new Set(["region", "town", "tavern"]));
  });

  it("collapsing one of two parents does not hide a child reachable through the other", () => {
    const entities = [entity("guild"), entity("watch"), entity("npc_a")];
    const index = buildHierarchy([
      edge("guild", "npc_a", "contains"),
      edge("npc_a", "watch", "member_of"),
    ]);
    const { visibleIds, hiddenDescendantCount } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["guild"]),
    );
    expect(visibleIds).toEqual(new Set(["guild", "watch", "npc_a"]));
    // Nothing is actually hidden yet — the watch path is still open — so the
    // collapsed guild shouldn't claim it's hiding anything.
    expect(hiddenDescendantCount.has("guild")).toBe(false);
  });

  it("collapsing every parent hides a child with multiple parents", () => {
    const entities = [entity("guild"), entity("watch"), entity("npc_a")];
    const index = buildHierarchy([
      edge("guild", "npc_a", "contains"),
      edge("npc_a", "watch", "member_of"),
    ]);
    const { visibleIds, hiddenDescendantCount } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["guild", "watch"]),
    );
    expect(visibleIds).toEqual(new Set(["guild", "watch"]));
    expect(hiddenDescendantCount.get("guild")).toBe(1);
    expect(hiddenDescendantCount.get("watch")).toBe(1);
  });

  it("collapsing the promoted root of a cycle hides the other member", () => {
    const entities = [entity("a"), entity("b")];
    const index = buildHierarchy([
      edge("a", "b", "contains"),
      edge("b", "a", "contains"),
    ]);
    // "a" is promoted to root (see buildForest's own cycle test) — collapsing
    // it must still terminate and hide exactly "b", not loop forever.
    const collapsed = computeHierarchyVisibility(entities, index, new Set(["a"]));
    expect(collapsed.visibleIds).toEqual(new Set(["a"]));
    const expanded = computeHierarchyVisibility(entities, index, new Set());
    expect(expanded.visibleIds).toEqual(new Set(["a", "b"]));
  });

  it("collapses an inverse-typed hierarchy edge the same way as a forward one", () => {
    const entities = [entity("faction"), entity("npc_b")];
    const index = buildHierarchy([edge("npc_b", "faction", "member_of")]);
    const { visibleIds } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["faction"]),
    );
    expect(visibleIds).toEqual(new Set(["faction"]));
  });

  it("never hides an entity that has no hierarchy children, even if collapsed", () => {
    const entities = [entity("item")];
    const index = buildHierarchy([]);
    const { visibleIds, hiddenDescendantCount } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["item"]),
    );
    expect(visibleIds).toEqual(new Set(["item"]));
    expect(hiddenDescendantCount.size).toBe(0);
  });

  it("only reasons about entities in the given (e.g. Focused-mode) base view", () => {
    // "tavern" exists in the wider project (the edge references it) but is
    // outside this base view — Focused mode must not silently pull it in.
    const entities = [entity("region"), entity("town")];
    const index = buildHierarchy([
      edge("town", "region", "located_in"),
      edge("tavern", "town", "located_in"),
    ]);
    const { visibleIds } = computeHierarchyVisibility(entities, index, new Set());
    expect(visibleIds).toEqual(new Set(["region", "town"]));
  });

  it("ignores a stale collapsed id that matches nothing in this project", () => {
    const entities = [entity("faction"), entity("npc_a")];
    const index = buildHierarchy([edge("faction", "npc_a", "contains")]);
    const { visibleIds, hiddenDescendantCount } = computeHierarchyVisibility(
      entities,
      index,
      new Set(["deleted_ghost"]),
    );
    expect(visibleIds).toEqual(new Set(["faction", "npc_a"]));
    expect(hiddenDescendantCount.size).toBe(0);
  });
});

describe("filterVisibleEdges", () => {
  it("drops an ordinary edge when either endpoint is hidden", () => {
    const edges = [edge("a", "b", "ally_of"), edge("b", "c", "enemy_of")];
    const kept = filterVisibleEdges(edges, new Set(["a", "b"]));
    expect(kept.map((e) => e.id)).toEqual([edges[0].id]);
  });

  it("keeps every edge whose endpoints are both visible", () => {
    const edges = [edge("a", "b", "ally_of"), edge("b", "c", "enemy_of")];
    const kept = filterVisibleEdges(edges, new Set(["a", "b", "c"]));
    expect(kept).toEqual(edges);
  });
});

describe("wouldCycle", () => {
  const index = buildHierarchy([
    edge("region", "town", "contains"),
    edge("town", "tavern", "contains"),
  ]);

  it("rejects dropping a folder into its own descendant", () => {
    expect(wouldCycle(index, "tavern", "region")).toBe(true);
    expect(wouldCycle(index, "town", "region")).toBe(true);
  });

  it("rejects dropping an entity onto itself", () => {
    expect(wouldCycle(index, "town", "town")).toBe(true);
  });

  it("allows an unrelated pair", () => {
    expect(wouldCycle(index, "region", "tavern")).toBe(false);
  });
});
