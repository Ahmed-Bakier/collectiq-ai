import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ActionRecord,
  AgentRunResponse,
  AutopilotRunResponse,
  AutopilotSettings,
  AutopilotSettingsUpdate,
  ApprovalStatus,
  AuditEvent,
  InsightsResponse,
  InvoiceAnalysisResponse,
  PayPalStatus,
} from "./types";

export function useInvoiceAnalysis() {
  return useQuery({
    queryKey: ["invoice-analysis"],
    queryFn: () => apiFetch<InvoiceAnalysisResponse>("/invoices/analysis"),
    staleTime: 30_000,
  });
}

export function usePayPalStatus() {
  return useQuery({
    queryKey: ["paypal-status"],
    queryFn: () => apiFetch<PayPalStatus>("/integrations/paypal/status"),
    refetchInterval: 60_000,
  });
}

export function useActions(approvalStatus?: ApprovalStatus) {
  const query = approvalStatus ? `?approval_status=${approvalStatus}` : "";
  return useQuery({
    queryKey: ["actions", approvalStatus ?? "all"],
    queryFn: () => apiFetch<{ items: ActionRecord[] }>(`/actions${query}`),
    refetchInterval: 15_000,
  });
}

export function useAction(actionId: string) {
  return useQuery({
    queryKey: ["action", actionId],
    queryFn: () => apiFetch<ActionRecord>(`/actions/${actionId}`),
  });
}

export function useAuditEvents(limit = 200) {
  return useQuery({
    queryKey: ["audit", limit],
    queryFn: () => apiFetch<{ items: AuditEvent[] }>(`/audit?limit=${limit}`),
    refetchInterval: 10_000,
  });
}

export function useAgentRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: string) =>
      apiFetch<AgentRunResponse>("/agent/runs", { method: "POST", body: JSON.stringify({ message }) }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["actions"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

// Approve / reject / execute: the backend enforces every rule; the UI only reflects results.
function useActionMutation<TVariables>(request: (variables: TVariables) => Promise<ActionRecord>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (action) => {
      queryClient.setQueryData(["action", action.id], action);
    },
    onSettled: () => {
      for (const key of ["action", "actions", "audit", "invoice-analysis"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useApproveAction() {
  return useActionMutation(({ id, parametersHash }: { id: string; parametersHash: string }) =>
    apiFetch<ActionRecord>(`/actions/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ parameters_hash: parametersHash }),
    }),
  );
}

export function useRejectAction() {
  return useActionMutation(({ id, reason }: { id: string; reason?: string }) =>
    apiFetch<ActionRecord>(`/actions/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  );
}

export function useExecuteAction() {
  return useActionMutation((id: string) => apiFetch<ActionRecord>(`/actions/${id}/execute`, { method: "POST" }));
}

export type MessageTone = "friendly" | "firm" | "final_notice";

// Editing creates a NEW action version on the backend; it needs its own approval.
export function useReviseAction() {
  return useActionMutation(({ id, message }: { id: string; message: string }) =>
    apiFetch<ActionRecord>(`/actions/${id}/revise`, {
      method: "POST",
      body: JSON.stringify({ message_to_client: message }),
    }),
  );
}

export function useRedraftAction() {
  return useActionMutation(({ id, tone, language }: { id: string; tone: MessageTone; language: string }) =>
    apiFetch<ActionRecord>(`/actions/${id}/redraft`, {
      method: "POST",
      body: JSON.stringify({ tone, language }),
    }),
  );
}

// ---------- Collection Autopilot ----------

export function useAutopilotSettings() {
  return useQuery({
    queryKey: ["autopilot-settings"],
    queryFn: () => apiFetch<AutopilotSettings>("/autopilot/settings"),
  });
}

export function useUpdateAutopilotSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (update: AutopilotSettingsUpdate) =>
      apiFetch<AutopilotSettings>("/autopilot/settings", { method: "PUT", body: JSON.stringify(update) }),
    onSuccess: (settings) => {
      queryClient.setQueryData(["autopilot-settings"], settings);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

// Runs the playbook now. Proposals still need approval unless the strict auto-approve policy applies.
export function useRunAutopilot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<AutopilotRunResponse>("/autopilot/run", { method: "POST" }),
    onSettled: () => {
      for (const key of ["actions", "action", "audit", "invoice-analysis", "autopilot-settings"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

// ---------- Client payment intelligence (read-only) ----------

export function useInsights() {
  return useQuery({
    queryKey: ["insights"],
    queryFn: () => apiFetch<InsightsResponse>("/insights"),
    staleTime: 60_000,
  });
}
