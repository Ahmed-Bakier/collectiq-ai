import { Route, Routes } from "react-router";
import { AppLayout } from "./components/layout/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route
          path="invoices"
          element={<PlaceholderPage title="Invoices" description="Searchable invoice table with filters." />}
        />
        <Route
          path="assistant"
          element={<PlaceholderPage title="AI Assistant" description="Chat with the collection agent and review its proposals." />}
        />
        <Route
          path="approvals"
          element={<PlaceholderPage title="Approvals" description="Approve, reject and execute proposed actions." />}
        />
        <Route
          path="activity"
          element={<PlaceholderPage title="Activity Log" description="Complete audit trail of agent, user and system events." />}
        />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="*" element={<PlaceholderPage title="Page not found" description="This page does not exist." />} />
      </Route>
    </Routes>
  );
}
