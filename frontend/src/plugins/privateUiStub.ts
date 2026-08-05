/**
 * No-op default for the optional `@loregraph/private-ui` package. vite.config.ts
 * aliases the import specifier here when the private package isn't installed,
 * so Sidebar/App can import from "@loregraph/private-ui" unconditionally —
 * the alias always resolves, and this stub contributes nothing to the build.
 *
 * A real `@loregraph/private-ui` package (separate private repo) must export
 * the same two names with the same shapes; TypeScript structural typing does
 * the rest, no shared types package needed.
 */
import type { IconName } from "../components/ui/Icon";
import type { RouteObject } from "react-router-dom";

export interface PrivateNavItem {
  to: string;
  icon: IconName;
  label: string;
  end?: boolean;
}

export const privateNavItems: PrivateNavItem[] = [];
export const privateRoutes: RouteObject[] = [];
