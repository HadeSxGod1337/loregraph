import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import i18n from "../i18n";

// Deterministic regardless of the test runner's locale/navigator — the app
// itself defaults visitors to ru via i18next-browser-languagedetector, so
// component tests assert against the same strings a real user sees.
void i18n.changeLanguage("ru");

afterEach(() => {
  cleanup();
});
