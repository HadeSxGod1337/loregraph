import { Route, Routes } from "react-router-dom";

import "./App.css";
import { Layout } from "./components/layout/Layout";
import { EntityEditPage } from "./pages/EntityEditPage";
import { EntityListPage } from "./pages/EntityListPage";
import { GraphViewPage } from "./pages/GraphViewPage";

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<EntityListPage />} />
        <Route path="/entities/new" element={<EntityEditPage />} />
        <Route path="/entities/:id" element={<EntityEditPage />} />
        <Route path="/graph" element={<GraphViewPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
