import type { ReactNode } from "react";
import { Link } from "react-router";
import { errorMessage } from "../../api/client";
import { useAutopilotSettings, useInsights } from "../../api/hooks";
import type { CashFlowForecast, ClientInsight } from "../../api/types";
import { formatDateTime, formatMoney } from "../../lib/format";
import { Card, CardTitle, EmptyState, ErrorState, LoadingState } from "../common/ui";
import { ForecastChart } from "./ForecastChart";
import { RiskBadge } from "./RiskBadge";

const LINK = "text-xs font-medium text-brand hover:underline";

/** Dashboard section: 30-day forecast, clients to watch and autopilot status. */
export function InsightsSection() {
  const insights = useInsights();

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardTitle
          title="Expected collections · next 30 days"
          subtitle="Estimate based on each client's PayPal payment history"
        />
        <div className="px-5 py-4">
          {insights.isPending && <LoadingState label="Building forecast from PayPal payment history…" />}
          {insights.isError && (
            <ErrorState message={errorMessage(insights.error)} onRetry={() => insights.refetch()} />
          )}
          {insights.data && <ForecastBody forecast={insights.data.forecast} />}
        </div>
      </Card>

      <div className="space-y-6 lg:col-span-2">
        <ClientsToWatch clients={insights.data?.clients} loading={insights.isPending} />
        <AutopilotCard />
      </div>
    </div>
  );
}

function ForecastBody({ forecast }: { forecast: CashFlowForecast }) {
  const currency = forecast.currency_code ?? "USD";
  if (Number(forecast.total_open) === 0) {
    return <EmptyState title="No open invoices" description="Sent invoices appear in the forecast." />;
  }
  const laterOrUnscheduled = Number(forecast.expected_later) + Number(forecast.unscheduled_amount);

  return (
    <>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Figure label="Expected in 30 days" value={formatMoney(forecast.expected_within_horizon, currency)} />
        <Figure label="At risk" value={formatMoney(forecast.at_risk_amount, currency)} swatch="bg-warning" />
        <Figure label="Later or no due date" value={formatMoney(String(laterOrUnscheduled), currency)} />
      </dl>
      <div className="mt-6">
        <ForecastChart forecast={forecast} />
      </div>
      <p className="mt-3 text-xs text-muted">{forecast.method}</p>
    </>
  );
}

function ClientsToWatch({ clients, loading }: { clients: ClientInsight[] | undefined; loading: boolean }) {
  const watch = (clients ?? [])
    .filter((client) => client.risk_level === "high" || client.risk_level === "medium")
    .slice(0, 4);

  return (
    <Card>
      <CardTitle
        title="Clients to watch"
        subtitle="Usually pay late, based on PayPal payment history"
        action={
          <Link to="/clients" className={LINK}>
            All clients
          </Link>
        }
      />
      {!clients ? (
        <p className="px-5 py-4 text-sm text-muted">{loading ? "Loading…" : "Client insights are unavailable."}</p>
      ) : watch.length === 0 ? (
        <EmptyState title="No late payers" description="Every client with payment history pays on time." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {watch.map((client) => (
            <li key={client.client} className="flex items-start justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{client.client}</p>
                <p className="text-xs text-muted">
                  {client.avg_days_late !== null
                    ? `Pays ${client.avg_days_late.toFixed(1)} days late on average`
                    : client.risk_reasons[0]}
                </p>
              </div>
              <RiskBadge level={client.risk_level} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AutopilotCard() {
  const settings = useAutopilotSettings();
  const data = settings.data;

  return (
    <Card>
      <CardTitle
        title="Collection Autopilot"
        subtitle="Playbook-driven follow-ups, approved by you"
        action={
          <Link to="/autopilot" className={LINK}>
            Open
          </Link>
        }
      />
      <div className="px-5 py-4">
        {!data ? (
          <p className="text-sm text-muted">{settings.isError ? "Autopilot status is unavailable." : "Loading…"}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Detail
              label="Status"
              value={
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className={`size-2 rounded-full ${data.enabled ? "bg-success" : "bg-warning"}`} />
                  {data.enabled ? "On" : "Paused"}
                </span>
              }
            />
            <Detail
              label="Auto-approve"
              value={data.auto_approve_enabled ? `Up to ${formatMoney(data.auto_approve_max_amount, "USD")}` : "Off"}
            />
            <Detail label="Last run" value={data.last_run_at ? formatDateTime(data.last_run_at) : "Never"} />
            <Detail
              label="Schedule"
              value={data.schedule_interval_minutes > 0 ? `Every ${data.schedule_interval_minutes} min` : "Manual"}
            />
          </dl>
        )}
      </div>
    </Card>
  );
}

function Figure({ label, value, swatch }: { label: string; value: string; swatch?: string }) {
  return (
    <div className="rounded-lg bg-surface px-3 py-2">
      <dt className="flex items-center gap-1.5 text-xs text-muted">
        {swatch && <span aria-hidden className={`size-2 rounded-sm ${swatch}`} />}
        {label}
      </dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  );
}
