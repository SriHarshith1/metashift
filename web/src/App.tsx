import { HashRouter, Route, Routes } from "react-router-dom";
import GameRedirect from "./components/GameRedirect";
import Layout from "./components/Layout";
import EntityHistory from "./pages/EntityHistory";
import PatchList from "./pages/PatchList";
import ReportPage from "./pages/ReportPage";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<GameRedirect />} />
          <Route path=":game" element={<PatchList />} />
          <Route path=":game/:patch" element={<ReportPage />} />
          <Route path=":game/:entityType/:entity" element={<EntityHistory />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
