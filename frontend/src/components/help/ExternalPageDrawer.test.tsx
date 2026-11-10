import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/renderWithProviders";
import { ExternalPageDrawer } from "./ExternalPageDrawer";

const URL = "https://cuddly-wound-d01.notion.site/example";
const EMBED_URL = "https://cuddly-wound-d01.notion.site/ebd/example";

function getIframe() {
  return document.querySelector("iframe.embed-overlay-iframe") as HTMLIFrameElement | null;
}

describe("ExternalPageDrawer", () => {
  it("shows a loading state and the title before the frame loads", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} embedUrl={EMBED_URL} onClose={vi.fn()} />,
    );
    expect(screen.getByRole("dialog", { name: "Project Hub" })).toBeInTheDocument();
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
    expect(getIframe()).toHaveAttribute("src", EMBED_URL);
  });

  it("points the persistent header link at the canonical url with a safe rel", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} embedUrl={EMBED_URL} onClose={vi.fn()} />,
    );
    const link = screen.getByRole("link", { name: /Открыть в новой вкладке/i });
    expect(link).toHaveAttribute("href", URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });

  it("omits allow-forms from the sandbox unless the page needs it", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} embedUrl={EMBED_URL} onClose={vi.fn()} />,
    );
    expect(getIframe()).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox",
    );
  });

  it("adds allow-forms for embeds that need to submit", () => {
    renderWithProviders(
      <ExternalPageDrawer
        title="Feedback"
        url={URL}
        embedUrl={EMBED_URL}
        allowForms
        onClose={vi.fn()}
      />,
    );
    expect(getIframe()).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms",
    );
  });

  it("shows the frame and a secondary escape hatch once it loads", async () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} embedUrl={EMBED_URL} onClose={vi.fn()} />,
    );
    fireEvent.load(getIframe()!);

    await waitFor(() => {
      expect(getIframe()).not.toHaveClass("embed-overlay-iframe-hidden");
    });
    const hint = document.querySelector<HTMLElement>(".embed-overlay-hint")!;
    expect(within(hint).getByRole("link")).toHaveAttribute("href", URL);
  });

  it("falls back to 'open in a new tab' if the frame never loads at all", async () => {
    renderWithProviders(
      <ExternalPageDrawer
        title="Project Hub"
        url={URL}
        embedUrl={EMBED_URL}
        onClose={vi.fn()}
        maxWaitMs={30}
      />,
    );

    await waitFor(() => {
      expect(getIframe()).not.toBeInTheDocument();
    });
    const fallback = document.querySelector<HTMLElement>(".embed-overlay-fallback")!;
    expect(within(fallback).getByRole("link")).toHaveAttribute("href", URL);
  });

  it("closes on Escape, close button, and backdrop click but not on inner clicks", () => {
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <ExternalPageDrawer
        title="Project Hub"
        url={URL}
        embedUrl={EMBED_URL}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(container.querySelector(".embed-overlay-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});
