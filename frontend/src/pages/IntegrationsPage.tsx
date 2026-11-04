import type { ReactNode } from "react";
import { Plug, RefreshCw } from "lucide-react";
import { errorMessage } from "../api/client";
import { usePayPalStatus } from "../api/hooks";
import { Card, ConnectionBadge, ErrorState, LoadingState, PageHeader } from "../components/common/ui";
import { formatDateTime } from "../lib/format";

export function IntegrationsPage() {
  const paypal = usePayPalStatus();

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Connections used by CollectIQ. Credentials stay on the server and are never sent to the browser."
      />

      <Card className="max-w-2xl p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div aria-hidden className="grid size-10 place-items-center rounded-lg bg-brand/10 text-brand">
              <Plug className="size-5" />
            </div>
            <div>
              <h2 className="font-semibold text-ink">PayPal Invoicing API</h2>
              <p className="text-sm text-muted">Source of truth for invoice data and status</p>
            </div>
          </div>
          {paypal.data && <ConnectionBadge connected={paypal.data.connected} />}
        </div>

        {paypal.isPending && <LoadingState label="Checking PayPal connection…" />}
        {paypal.isError && <div className="mt-4"><ErrorState message={errorMessage(paypal.error)} /></div>}

        {paypal.data && (
          <dl className="mt-5 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
            <Field label="Environment" value={<span className="uppercase">{paypal.data.environment}</span>} />
            <Field label="Credentials configured" value={paypal.data.credentials_configured ? "Yes" : "No"} />
            <Field label="PayPal app ID" value={paypal.data.app_id ?? "—"} />
            <Field label="Last checked" value={formatDateTime(paypal.data.checked_at)} />
          </dl>
        )}

        {paypal.data?.error && (
          <div role="alert" className="mt-4 rounded-lg border border-danger/20 bg-danger/5 p-3 text-sm text-danger">
            <p className="font-medium">{paypal.data.error}</p>
            <p className="mt-1 text-danger/80">
              Check PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env, then restart the backend.
            </p>
          </div>
        )}

        <button
          type="button"
          onClick={() => paypal.refetch()}
          disabled={paypal.isFetching}
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-ink hover:bg-slate-50 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
        >
          <RefreshCw className={`size-4 ${paypal.isFetching ? "animate-spin" : ""}`} aria-hidden />
          Check again
        </button>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 font-medium text-ink">{value}</dd>
    </div>
  );
}
