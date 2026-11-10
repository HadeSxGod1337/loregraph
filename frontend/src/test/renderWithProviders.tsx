import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

/** Wraps a component with the providers page/dialog tests need: a router
 * for `<Link>`. Data hooks are mocked per test file, so no
 * QueryClientProvider is required here — add one locally if a test ever
 * exercises the real react-query hooks instead of mocking them. */
export function renderWithProviders(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}
