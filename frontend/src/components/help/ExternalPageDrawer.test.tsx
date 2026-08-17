import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/renderWithProviders";
import { ExternalPageDrawer } from "./ExternalPageDrawer";

const URL = "https://cuddly-wound-d01.notion.site/example";

function getIframe() {
  return document.querySelector("iframe.embed-overlay-iframe") as HTMLIFrameElement | null;
}

describe("ExternalPageDrawer", () => {
  it("shows a loading state and the title before the frame settles", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} onClose={vi.fn()} />,
    );
    expect(screen.getByRole("dialog", { name: "Project Hub" })).toBeInTheDocument();
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("points the persistent link at the real url with a safe rel", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} onClose={vi.fn()} />,
    );
    const link = screen.getByRole("link", { name: /Открыть в новой вкладке/i });
    expect(link).toHaveAttribute("href", URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });

  it("omits allow-forms from the sandbox unless the page needs it", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} onClose={vi.fn()} />,
    );
    expect(getIframe()).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox",
    );
  });

  it("adds allow-forms for embeds that need to submit", () => {
    renderWithProviders(
      <ExternalPageDrawer title="Feedback" url={URL} allowForms onClose={vi.fn()} />,
    );
    expect(getIframe()).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms",
    );
  });

  it("falls back to 'open in a new tab' when the frame settles suspiciously fast", async () => {
    renderWithProviders(
      <ExternalPageDrawer
        title="Project Hub"
        url={URL}
        onClose={vi.fn()}
        minEmbedMs={50}
        maxWaitMs={5000}
      />,
    );
    // A blocked frame still fires `load` — just almost immediately.
    fireEvent.load(getIframe()!);

    await waitFor(() => {
      expect(getIframe()).not.toBeInTheDocument();
    });
    const fallback = document.querySelector<HTMLElement>(".embed-overlay-fallback")!;
    expect(within(fallback).getByRole("link")).toHaveAttribute("href", URL);
  });

  it("keeps the iframe once it settles past the minimum window", async () => {
    renderWithProviders(
      <ExternalPageDrawer
        title="Project Hub"
        url={URL}
        onClose={vi.fn()}
        minEmbedMs={10}
        maxWaitMs={5000}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 40));
    fireEvent.load(getIframe()!);

    await waitFor(() => {
      expect(getIframe()).not.toHaveClass("embed-overlay-iframe-hidden");
    });
  });

  it("closes on Escape, close button, and backdrop click but not on inner clicks", () => {
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <ExternalPageDrawer title="Project Hub" url={URL} onClose={onClose} />,
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
