import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Project } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { ProjectListPage } from "./ProjectListPage";

function project(overrides: Partial<Project> & { id: string; name: string }): Project {
  return {
    description: null,
    agent_instructions: null,
    entity_count: 0,
    edge_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

let projectsState: { data: Project[] | undefined; isLoading: boolean; error: unknown };
let lastProjectId: string | null;
const createMutate = vi.fn();
const deleteMutate = vi.fn();
const importMutate = vi.fn();

function resetState() {
  projectsState = { data: [], isLoading: false, error: null };
  lastProjectId = null;
}
resetState();

vi.mock("../hooks/useProjects", () => ({
  useProjects: () => projectsState,
  useCreateProject: () => ({ mutate: createMutate, isPending: false, isError: false, error: null }),
  useDeleteProject: () => ({ mutate: deleteMutate, isPending: false }),
  useImportProject: () => ({ mutate: importMutate, isPending: false, isError: false, error: null }),
}));

vi.mock("../hooks/useLastProject", () => ({
  useLastProject: () => lastProjectId,
}));

beforeEach(() => {
  resetState();
  createMutate.mockReset();
  deleteMutate.mockReset();
  importMutate.mockReset();
});

describe("ProjectListPage", () => {
  it("shows the empty state with primary and secondary CTAs when there are no projects", () => {
    renderWithProviders(<ProjectListPage />);

    expect(screen.getByText("Пока нет проектов.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Создать проект/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Импортировать" })).toHaveLength(2);
    // No project count summary with zero projects.
    expect(screen.queryByText(/сущностей/)).not.toBeInTheDocument();
  });

  it("opens the create dialog from the empty state without crashing and closes on cancel", () => {
    renderWithProviders(<ProjectListPage />);

    fireEvent.click(screen.getByRole("button", { name: /Создать проект/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the create dialog from the header button without shifting the list", () => {
    projectsState = {
      data: [project({ id: "p1", name: "Ravenhollow", entity_count: 17, edge_count: 19 })],
      isLoading: false,
      error: null,
    };
    renderWithProviders(<ProjectListPage />);

    fireEvent.click(screen.getByRole("button", { name: "Новый проект" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The existing project is still rendered underneath the dialog, not
    // replaced by an inline form.
    expect(screen.getByText("Ravenhollow")).toBeInTheDocument();
  });

  it("renders the last-opened project as a distinct continue card, separate from the grid", () => {
    projectsState = {
      data: [
        project({ id: "p1", name: "Ravenhollow", entity_count: 17, edge_count: 19 }),
        project({ id: "p2", name: "Ashen Coast" }),
      ],
      isLoading: false,
      error: null,
    };
    lastProjectId = "p1";
    renderWithProviders(<ProjectListPage />);

    expect(screen.getByText("Последний проект")).toBeInTheDocument();
    // Two occurrences of the name: once in the continue card, once... no,
    // it should NOT also appear as a regular grid card.
    expect(screen.getAllByText("Ravenhollow")).toHaveLength(1);
    expect(screen.getByText("Ashen Coast")).toBeInTheDocument();
  });

  it("pluralizes the project count summary", () => {
    projectsState = {
      data: [project({ id: "p1", name: "Ravenhollow", entity_count: 5, edge_count: 0 })],
      isLoading: false,
      error: null,
    };
    renderWithProviders(<ProjectListPage />);

    expect(screen.getByText("1 проект · 5 сущностей")).toBeInTheDocument();
  });

  it("filters the grid by name once there are enough projects to show the filter", () => {
    projectsState = {
      data: [
        project({ id: "p1", name: "Ravenhollow" }),
        project({ id: "p2", name: "Ashen Coast" }),
        project({ id: "p3", name: "Ravenwood Keep" }),
        project({ id: "p4", name: "Frostmere Hold" }),
        project({ id: "p5", name: "Emberfall Wastes" }),
      ],
      isLoading: false,
      error: null,
    };
    renderWithProviders(<ProjectListPage />);

    const filterInput = screen.getByPlaceholderText("Фильтр по названию…");
    fireEvent.change(filterInput, { target: { value: "raven" } });

    expect(screen.getByText("Ravenhollow")).toBeInTheDocument();
    expect(screen.getByText("Ravenwood Keep")).toBeInTheDocument();
    expect(screen.queryByText("Ashen Coast")).not.toBeInTheDocument();
    expect(screen.queryByText("Frostmere Hold")).not.toBeInTheDocument();
  });

  it("shows a no-matches hint when the filter query matches nothing", () => {
    projectsState = {
      data: [
        project({ id: "p1", name: "Ravenhollow" }),
        project({ id: "p2", name: "Ashen Coast" }),
        project({ id: "p3", name: "Ravenwood Keep" }),
        project({ id: "p4", name: "Frostmere Hold" }),
        project({ id: "p5", name: "Emberfall Wastes" }),
      ],
      isLoading: false,
      error: null,
    };
    renderWithProviders(<ProjectListPage />);

    fireEvent.change(screen.getByPlaceholderText("Фильтр по названию…"), {
      target: { value: "nowhere" },
    });

    expect(screen.getByText("Проект «nowhere» не найден.")).toBeInTheDocument();
  });

  it("does not show the filter for four or fewer projects", () => {
    projectsState = {
      data: [
        project({ id: "p1", name: "Ravenhollow" }),
        project({ id: "p2", name: "Ashen Coast" }),
      ],
      isLoading: false,
      error: null,
    };
    renderWithProviders(<ProjectListPage />);

    expect(screen.queryByPlaceholderText("Фильтр по названию…")).not.toBeInTheDocument();
  });
});
