import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FEEDBACK_FORM_URL, PROJECT_HUB_URL } from "../lib/externalLinks";
import { renderWithProviders } from "../test/renderWithProviders";
import { HelpPage } from "./HelpPage";

describe("HelpPage support block", () => {
  it("opens the Project Hub drawer pointed at the public Notion page", () => {
    renderWithProviders(<HelpPage />);
    fireEvent.click(screen.getByRole("button", { name: /Project Hub/ }));

    const dialog = screen.getByRole("dialog", { name: "Project Hub" });
    expect(dialog.querySelector("iframe")).toHaveAttribute("src", PROJECT_HUB_URL);
  });

  it("opens the feedback drawer pointed at the public Notion form", () => {
    renderWithProviders(<HelpPage />);
    fireEvent.click(screen.getByRole("button", { name: /Оставить отзыв/ }));

    const dialog = screen.getByRole("dialog", { name: "Оставить отзыв" });
    expect(dialog.querySelector("iframe")).toHaveAttribute("src", FEEDBACK_FORM_URL);
  });

  it("swaps to the newly clicked target instead of stacking drawers", () => {
    renderWithProviders(<HelpPage />);
    fireEvent.click(screen.getByRole("button", { name: /Project Hub/ }));
    fireEvent.click(screen.getByRole("button", { name: /Оставить отзыв/ }));

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog", { name: "Оставить отзыв" })).toBeInTheDocument();
  });
});
