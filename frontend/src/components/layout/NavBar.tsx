import { NavLink } from "react-router-dom";

import { ThemePicker } from "./ThemePicker";

export function NavBar() {
  return (
    <nav className="navbar">
      <NavLink to="/" end className="navbar-brand">
        Loregraph
      </NavLink>
      <div className="navbar-links">
        <NavLink to="/" end>
          Entities
        </NavLink>
        <NavLink to="/graph">Graph</NavLink>
      </div>
      <ThemePicker />
    </nav>
  );
}
