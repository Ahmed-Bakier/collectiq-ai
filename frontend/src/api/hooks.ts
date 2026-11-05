import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ActionRecord,
  AgentRunResponse,
  ApprovalStatus,
  AuditEvent,
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
