import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { AssistantProvider } from "./components/agent/AssistantContext";
import { LoadingState } from "./components/common/ui";
import { AppLayout } from "./components/layout/AppLayout";
import { ActivityPage } from "./pages/ActivityPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AutopilotPage } from "./pages/AutopilotPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

// AG Grid is large, so the invoices page is loaded only when opened (separate chunk).
const InvoicesPage = lazy(() => import("./pages/InvoicesPage").then((module) => ({ default: module.InvoicesPage })));

export default function App() {
  return (
    <AssistantProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route
            path="invoices"
            element={
              <Suspense fallback={<LoadingState label="Loading invoices…" />}>
                <InvoicesPage />
              </Suspense>
            }
          />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="autopilot" element={<AutopilotPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="*" element={<PlaceholderPage title="Page not found" description="This page does not exist." />} />
        </Route>
      </Routes>
    </AssistantProvider>
  );
}
