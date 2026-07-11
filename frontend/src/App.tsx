import { Route, Routes } from "react-router-dom";

import "./App.css";
import { Layout } from "./components/layout/Layout";
import { AssistantPage } from "./pages/AssistantPage";
import { EntityEditPage } from "./pages/EntityEditPage";
import { EntityListPage } from "./pages/EntityListPage";
import { GraphViewPage } from "./pages/GraphViewPage";
import { ProjectListPage } from "./pages/ProjectListPage";

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ProjectListPage />} />
        <Route path="/projects/:projectId/entities" element={<EntityListPage />} />
        <Route path="/projects/:projectId/entities/new" element={<EntityEditPage />} />
        <Route path="/projects/:projectId/entities/:id" element={<EntityEditPage />} />
        <Route path="/projects/:projectId/graph" element={<GraphViewPage />} />
        <Route path="/projects/:projectId/assistant" element={<AssistantPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
