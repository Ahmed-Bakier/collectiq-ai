import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { InvoiceAnalysisResponse, PayPalStatus } from "./types";

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
