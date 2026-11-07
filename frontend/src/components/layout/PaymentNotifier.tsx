import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, X } from "lucide-react";
import { apiFetch } from "../../api/client";
import type { AuditEvent } from "../../api/types";

const POLL_MS = 10_000;
const TOAST_MS = 12_000;
const REFRESH_KEYS = ["invoice-analysis", "insights", "actions", "action", "audit", "safety"];

/** Shows "Payment received" when PayPal reports a payment (webhook → audit trail) and refreshes the data. */
export function PaymentNotifier() {
  const queryClient = useQueryClient();
  const seen = useRef<Set<number> | null>(null);
  const [toasts, setToasts] = useState<AuditEvent[]>([]);

  useQuery({
    queryKey: ["payment-events"],
    queryFn: async () => {
      const { items } = await apiFetch<{ items: AuditEvent[] }>("/audit?limit=20");
      const payments = items.filter((event) => event.event_type === "payment_received");
      if (seen.current === null) {
        // First load: remember existing payments without announcing them.
        seen.current = new Set(payments.map((event) => event.id));
        return payments.length;
      }
      const known = seen.current;
      const fresh = payments.filter((event) => !known.has(event.id));
      if (fresh.length > 0) {
        fresh.forEach((event) => known.add(event.id));
        setToasts((current) => [...fresh, ...current].slice(0, 3));
        for (const key of REFRESH_KEYS) {
          void queryClient.invalidateQueries({ queryKey: [key] });
        }
      }
      return payments.length;
    },
    refetchInterval: POLL_MS,
  });

  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => setToasts((current) => current.slice(0, -1)), TOAST_MS);
    return () => clearTimeout(timer);
  }, [toasts]);

  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((event) => (
        <div
          key={event.id}
          role="status"
          className="pointer-events-auto flex items-start gap-3 rounded-xl border border-success/25 bg-white p-4 shadow-lg"
        >
          <BadgeCheck className="mt-0.5 size-5 shrink-0 text-success" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">Payment received</p>
            <p className="mt-0.5 text-xs text-muted">{event.message}</p>
          </div>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => setToasts((current) => current.filter((toast) => toast.id !== event.id))}
            className="rounded p-0.5 text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
