import { Route, Routes } from "react-router";
import { AssistantProvider } from "./components/agent/AssistantContext";
import { AppLayout } from "./components/layout/AppLayout";
import { ActivityPage } from "./pages/ActivityPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

export default function App() {
  return (
    <AssistantProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route
            path="invoices"
            element={<PlaceholderPage title="Invoices" description="Searchable invoice table with filters." />}
          />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="*" element={<PlaceholderPage title="Page not found" description="This page does not exist." />} />
        </Route>
      </Routes>
    </AssistantProvider>
  );
}
