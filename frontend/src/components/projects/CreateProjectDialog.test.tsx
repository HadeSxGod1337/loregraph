import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/renderWithProviders";
import { CreateProjectDialog } from "./CreateProjectDialog";

const mutate = vi.fn();
let mutationState: { isPending: boolean; isError: boolean; error: unknown };

function resetMutationState() {
  mutationState = { isPending: false, isError: false, error: null };
}
resetMutationState();

vi.mock("../../hooks/useProjects", () => ({
  useCreateProject: () => ({
    mutate,
    isPending: mutationState.isPending,
    isError: mutationState.isError,
    error: mutationState.error,
  }),
}));

beforeEach(() => {
  mutate.mockReset();
  resetMutationState();
});

describe("CreateProjectDialog", () => {
  it("autofocuses the name field", () => {
    renderWithProviders(<CreateProjectDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(screen.getByPlaceholderText("Название")).toHaveFocus();
  });

  it("disables the submit button until a name is entered", () => {
    renderWithProviders(<CreateProjectDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    const submit = screen.getByRole("button", { name: "Создать" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Название"), {
      target: { value: "Ravenhollow" },
    });
    expect(submit).not.toBeDisabled();
  });

  it("submits the trimmed name and description on Enter", () => {
    renderWithProviders(<CreateProjectDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("Название"), {
      target: { value: "  Ravenhollow  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Описание (необязательно)"), {
      target: { value: "  A dark-fantasy town  " },
    });
    fireEvent.keyDown(screen.getByPlaceholderText("Название"), { key: "Enter" });

    expect(mutate).toHaveBeenCalledWith(
      { name: "Ravenhollow", description: "A dark-fantasy town" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("does not submit on Enter while the name is blank", () => {
    renderWithProviders(<CreateProjectDialog onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.keyDown(screen.getByPlaceholderText("Название"), { key: "Enter" });
    expect(mutate).not.toHaveBeenCalled();
  });

  it("calls onCreated once the mutation succeeds", () => {
    const onCreated = vi.fn();
    mutate.mockImplementation((_data, opts: { onSuccess: () => void }) => opts.onSuccess());
    renderWithProviders(<CreateProjectDialog onClose={vi.fn()} onCreated={onCreated} />);

    fireEvent.change(screen.getByPlaceholderText("Название"), {
      target: { value: "Ravenhollow" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    expect(onCreated).toHaveBeenCalledWith("Ravenhollow");
  });

  it("shows an inline error and keeps the dialog open when the mutation fails", () => {
    mutationState = { isPending: false, isError: true, error: new Error("Network unreachable") };
    const onClose = vi.fn();
    renderWithProviders(<CreateProjectDialog onClose={onClose} onCreated={vi.fn()} />);

    expect(screen.getByText("Network unreachable")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on Escape without creating a project", () => {
    const onClose = vi.fn();
    renderWithProviders(<CreateProjectDialog onClose={onClose} onCreated={vi.fn()} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("closes when Cancel is clicked", () => {
    const onClose = vi.fn();
    renderWithProviders(<CreateProjectDialog onClose={onClose} onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is clicked, but not on clicks inside the dialog", () => {
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <CreateProjectDialog onClose={onClose} onCreated={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(container.querySelector(".dialog-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
