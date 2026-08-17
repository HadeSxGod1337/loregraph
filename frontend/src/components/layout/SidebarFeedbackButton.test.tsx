import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/renderWithProviders";
import { SidebarFeedbackButton } from "./SidebarFeedbackButton";

describe("SidebarFeedbackButton", () => {
  it("shows a label when the sidebar is expanded", () => {
    renderWithProviders(<SidebarFeedbackButton collapsed={false} />);
    expect(screen.getByRole("button", { name: "Отзыв" })).toBeInTheDocument();
    expect(screen.getByText("Отзыв")).toBeInTheDocument();
  });

  it("keeps an accessible label when collapsed to icon-only", () => {
    renderWithProviders(<SidebarFeedbackButton collapsed />);
    expect(screen.getByRole("button", { name: "Отзыв" })).toBeInTheDocument();
    expect(screen.queryByText("Отзыв")).not.toBeInTheDocument();
  });

  it("opens the feedback drawer on click and closes it again", () => {
    renderWithProviders(<SidebarFeedbackButton collapsed={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Отзыв" }));
    expect(screen.getByRole("dialog", { name: "Оставить отзыв" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
