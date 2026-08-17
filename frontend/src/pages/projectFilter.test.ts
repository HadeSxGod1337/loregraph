import { describe, expect, it } from "vitest";

import type { Project } from "../api/types";
import { filterProjects } from "./projectFilter";

function project(id: string, name: string): Project {
  return {
    id,
    name,
    description: null,
    agent_instructions: null,
    entity_count: 0,
    edge_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("filterProjects", () => {
  const projects = [
    project("1", "Ravenhollow"),
    project("2", "Ashen Coast"),
    project("3", "Ravenwood Keep"),
  ];

  it("returns everything when there is no exclusion or query", () => {
    expect(filterProjects(projects, undefined, "")).toHaveLength(3);
  });

  it("excludes the continue/last-opened project by id", () => {
    const result = filterProjects(projects, "1", "");
    expect(result.map((p) => p.id)).toEqual(["2", "3"]);
  });

  it("filters by a case-insensitive name substring", () => {
    const result = filterProjects(projects, undefined, "raven");
    expect(result.map((p) => p.id)).toEqual(["1", "3"]);
  });

  it("combines exclusion and query", () => {
    const result = filterProjects(projects, "1", "raven");
    expect(result.map((p) => p.id)).toEqual(["3"]);
  });

  it("trims whitespace in the query", () => {
    const result = filterProjects(projects, undefined, "  ashen  ");
    expect(result.map((p) => p.id)).toEqual(["2"]);
  });

  it("returns nothing when the query matches no project", () => {
    expect(filterProjects(projects, undefined, "nowhere")).toEqual([]);
  });
});
