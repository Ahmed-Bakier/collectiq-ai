import type { InvoiceSummary } from "../api/types";

/** Format a decimal string from the API for display only (no arithmetic). */
export function formatMoney(amount: string | null | undefined, currency: string | null | undefined): string {
  if (amount == null) return "—";
  const value = Number(amount);
  if (!Number.isFinite(value)) return amount;
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: currency ?? "USD" }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

/** Format YYYY-MM-DD (as a calendar date, no timezone shift) or an ISO timestamp. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function clientName(invoice: InvoiceSummary): string {
  return invoice.recipient_business_name ?? invoice.recipient_name ?? "Unknown client";
}
