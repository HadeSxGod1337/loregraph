import { Outlet, RouterProvider, createBrowserRouter } from "react-router-dom";

import "./App.css";
import { Layout } from "./components/layout/Layout";
import { AssistantPage } from "./pages/AssistantPage";
import { EntityEditPage } from "./pages/EntityEditPage";
import { EntityListPage } from "./pages/EntityListPage";
import { GraphViewPage } from "./pages/GraphViewPage";
import { HelpPage } from "./pages/HelpPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { ProjectSettingsPage } from "./pages/ProjectSettingsPage";

// Data router (not <BrowserRouter>) — pages with unsaved edits use
// useBlocker to intercept in-app navigation, which plain routers don't
// support.
const router = createBrowserRouter([
  {
    element: (
      <Layout>
        <Outlet />
      </Layout>
    ),
    children: [
      { path: "/", element: <ProjectListPage /> },
      { path: "/projects/:projectId/entities", element: <EntityListPage /> },
      { path: "/projects/:projectId/entities/new", element: <EntityEditPage /> },
      { path: "/projects/:projectId/entities/:id", element: <EntityEditPage /> },
      { path: "/projects/:projectId/graph", element: <GraphViewPage /> },
      { path: "/projects/:projectId/assistant", element: <AssistantPage /> },
      { path: "/projects/:projectId/settings", element: <ProjectSettingsPage /> },
      { path: "/projects/:projectId/help", element: <HelpPage /> },
    ],
  },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
