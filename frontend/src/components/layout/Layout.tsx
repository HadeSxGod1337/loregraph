import type { ReactNode } from "react";

import { NavBar } from "./NavBar";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="layout">
      <NavBar />
      <main className="layout-content">{children}</main>
    </div>
  );
}
