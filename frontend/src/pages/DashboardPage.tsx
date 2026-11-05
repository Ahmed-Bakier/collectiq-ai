import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowRight, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { useInvoiceAnalysis } from "../api/hooks";
import type { AnalyzedInvoice, CurrencyTotals, InvoiceAnalysisResponse, SuggestedAction } from "../api/types";
import {
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  PriorityBadge,
  StateBadge,
} from "../components/common/ui";
import { InsightsSection } from "../components/insights/InsightsSection";
import { clientName, formatDate, formatMoney } from "../lib/format";

const SUGGESTED_PROMPTS = [
  "Which invoices need my attention this week?",
  "Which clients are overdue and what should I do?",
  "Summarize my outstanding balance.",
  "Which clients usually pay late?",
  "How much will I collect in the next 30 days?",
];

const ACTION_LABELS: Record<SuggestedAction, string> = {
  send_reminder: "Suggested: send reminder",
  send_invoice: "Suggested: send invoice",
  monitor: "Monitor",
  review: "Needs review",
  none: "",
};

export function DashboardPage() {
  const analysis = useInvoiceAnalysis();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("");

  function askAgent(text: string) {
    const trimmed = text.trim();
    if (trimmed) navigate(`/assistant?q=${encodeURIComponent(trimmed)}`);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    askAgent(prompt);
  }

  return (
    <div>
      <PageHeader
        title="Collections overview"
        description={
          analysis.data
            ? `Live PayPal Sandbox data · as of ${formatDate(analysis.data.as_of)} (${analysis.data.timezone})`
            : "Live PayPal Sandbox data"
        }
      />

      <section className="mb-6 rounded-xl bg-navy p-5 text-white shadow-sm">
        <div className="flex items-center gap-2 text-sm font-medium text-white/80">
          <Sparkles className="size-4 text-accent" aria-hidden />
          Ask CollectIQ
        </div>
        <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label htmlFor="dashboard-prompt" className="sr-only">
            Ask the collection agent
          </label>
          <input
            id="dashboard-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="e.g. Which invoices need my attention this week?"
            className="flex-1 rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          />
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-navy hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Ask agent <ArrowRight className="size-4" aria-hidden />
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED_PROMPTS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => askAgent(suggestion)}
              className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/80 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </section>

      {analysis.isPending && <LoadingState label="Loading invoices from PayPal…" />}
      {analysis.isError && <ErrorState message={errorMessage(analysis.error)} onRetry={() => analysis.refetch()} />}
      {analysis.data && <DashboardContent data={analysis.data} />}
    </div>
  );
}

function DashboardContent({ data }: { data: InvoiceAnalysisResponse }) {
  const { summary } = data;
  const totals: CurrencyTotals = summary.totals_by_currency[0] ?? {
    currency_code: "USD",
    outstanding_amount: "0",
    overdue_amount: "0",
    draft_amount: "0",
  };
  const attention = data.invoices.filter((item) => item.suggested_action !== "none");
  const recent = [...data.invoices]
    .sort((a, b) => (b.invoice.invoice_date ?? "").localeCompare(a.invoice.invoice_date ?? ""))
    .slice(0, 5);

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Outstanding"
          value={formatMoney(totals.outstanding_amount, totals.currency_code)}
          hint={`${summary.open_count} open invoice(s)`}
        />
        <KpiCard
          label="Overdue"
          value={formatMoney(totals.overdue_amount, totals.currency_code)}
          hint={`${summary.overdue_count} overdue invoice(s)`}
          tone={summary.overdue_count > 0 ? "danger" : "default"}
        />
        <KpiCard
          label="Due soon"
          value={String(summary.due_soon_count)}
          hint={`Due within ${data.due_soon_window_days} days`}
          tone={summary.due_soon_count > 0 ? "warning" : "default"}
        />
        <KpiCard
          label="Drafts not sent"
          value={formatMoney(totals.draft_amount, totals.currency_code)}
          hint={`${summary.draft_count} draft(s)`}
        />
      </div>
      {summary.totals_by_currency.length > 1 && (
        <p className="mt-2 text-xs text-muted">
          Totals shown in {totals.currency_code}. Amounts in other currencies are not converted.
        </p>
      )}

      <InsightsSection />

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardTitle title="Needs attention" subtitle="Ranked by CollectIQ's deterministic priority score" />
          {attention.length === 0 ? (
            <EmptyState title="Nothing needs attention" description="All open invoices are on track." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {attention.map((item) => (
                <AttentionRow key={item.invoice.id} item={item} />
              ))}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <CardTitle
            title="Recent invoices"
            action={
              <Link to="/invoices" className="text-xs font-medium text-brand hover:underline">
                View all
              </Link>
            }
          />
          {recent.length === 0 ? (
            <EmptyState title="No invoices yet" description="Invoices created in PayPal Sandbox appear here." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {recent.map((item) => (
                <li key={item.invoice.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{clientName(item.invoice)}</p>
                    <p className="text-xs text-muted">
                      {item.invoice.invoice_number ?? item.invoice.id} · due {formatDate(item.invoice.due_date)}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="text-sm font-semibold tabular-nums">
                      {formatMoney(item.invoice.amount_due ?? item.invoice.total_amount, item.invoice.currency_code)}
                    </span>
                    <StateBadge state={item.collection_state} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

const KPI_TONES = {
  default: "text-ink",
  warning: "text-warning",
  danger: "text-danger",
} as const;

function KpiCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint: string;
  tone?: keyof typeof KPI_TONES;
}) {
  return (
    <Card className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${KPI_TONES[tone]}`}>{value}</p>
      <p className="mt-1 text-xs text-muted">{hint}</p>
    </Card>
  );
}

function AttentionRow({ item }: { item: AnalyzedInvoice }) {
  const { invoice } = item;
  return (
    <li className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-medium text-ink">{clientName(invoice)}</p>
          <StateBadge state={item.collection_state} />
          <PriorityBadge level={item.priority_level} score={item.priority_score} />
        </div>
        <p className="mt-1 text-xs text-muted">
          {invoice.invoice_number ?? invoice.id} · {item.reasons.slice(1).join(" · ")}
        </p>
      </div>
      <div className="shrink-0 sm:text-right">
        <p className="font-semibold tabular-nums text-ink">
          {formatMoney(invoice.amount_due ?? invoice.total_amount, invoice.currency_code)}
        </p>
        <p className="text-xs text-muted">{ACTION_LABELS[item.suggested_action]}</p>
      </div>
    </li>
  );
}
