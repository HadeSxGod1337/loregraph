import { NavLink } from "react-router-dom";

import { ThemePicker } from "./ThemePicker";

export function NavBar() {
  return (
    <nav className="navbar">
      <NavLink to="/" end className="navbar-brand">
        Loregraph
      </NavLink>
      <ThemePicker />
    </nav>
  );
}
