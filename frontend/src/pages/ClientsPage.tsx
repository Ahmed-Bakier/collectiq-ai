import { useNavigate } from "react-router";
import { MessageSquare } from "lucide-react";
import { errorMessage } from "../api/client";
import { useInsights } from "../api/hooks";
import type { ClientInsight } from "../api/types";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/common/ui";
import { RiskBadge } from "../components/insights/RiskBadge";
import { formatDate, formatMoney } from "../lib/format";

export function ClientsPage() {
  const insights = useInsights();
  const navigate = useNavigate();

  function askAbout(client: string) {
    const question = `How should I follow up with ${client}? Consider their PayPal payment history.`;
    navigate(`/assistant?q=${encodeURIComponent(question)}`);
  }

  return (
    <div>
      <PageHeader
        title="Clients"
        description={
          insights.data
            ? `Payment behaviour from PayPal payment history · as of ${formatDate(insights.data.as_of)}`
            : "Payment behaviour from PayPal payment history"
        }
      />

      {insights.isPending && <LoadingState label="Reading payment history from PayPal…" />}
      {insights.isError && <ErrorState message={errorMessage(insights.error)} onRetry={() => insights.refetch()} />}
      {insights.data &&
        (insights.data.clients.length === 0 ? (
          <Card>
            <EmptyState title="No clients yet" description="Clients appear once invoices exist in PayPal Sandbox." />
          </Card>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {insights.data.clients.map((insight) => (
              <ClientCard key={insight.client} insight={insight} onAsk={() => askAbout(insight.client)} />
            ))}
          </ul>
        ))}
    </div>
  );
}

function ClientCard({ insight, onAsk }: { insight: ClientInsight; onAsk: () => void }) {
  const currency = insight.currency_code ?? "USD";
  const rate = insight.on_time_rate;

  return (
    <li className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-semibold text-ink">{insight.client}</h2>
          <p className="text-xs text-muted">
            {insight.paid_count} paid · {insight.open_count} open
          </p>
        </div>
        <RiskBadge level={insight.risk_level} />
      </div>

      <div className="mt-4">
        <div className="flex justify-between gap-3 text-xs">
          <span className="text-muted">Paid on time</span>
          <span className="font-medium tabular-nums text-ink">
            {rate === null
              ? "No payment history"
              : `${Math.round(rate * 100)}% (${insight.on_time_count} of ${insight.paid_count})`}
          </span>
        </div>
        <div aria-hidden className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-accent/15">
          <div className="h-full rounded-full bg-accent" style={{ width: `${(rate ?? 0) * 100}%` }} />
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <Metric label="Avg days late" value={insight.avg_days_late === null ? "—" : insight.avg_days_late.toFixed(1)} />
        <Metric label="Open" value={formatMoney(insight.open_amount, currency)} />
        <Metric label="Overdue" value={formatMoney(insight.overdue_amount, currency)} />
      </dl>

      <ul className="mt-4 flex-1 list-disc space-y-1 pl-4 text-xs text-muted">
        {insight.risk_reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      <button
        type="button"
        onClick={onAsk}
        className="mt-4 inline-flex items-center justify-center gap-1.5 self-start rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <MessageSquare className="size-3.5" aria-hidden />
        Ask the agent about this client
      </button>
    </li>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}
