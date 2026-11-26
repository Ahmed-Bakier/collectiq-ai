import { useState, type FormEvent } from "react";
import { CircleCheck, CircleX, Lock, ShieldCheck } from "lucide-react";
import { errorMessage } from "../api/client";
import { useCheckMessage, useSafetyReport } from "../api/hooks";
import type { SafetyReport } from "../api/types";
import { Card, CardTitle, ErrorState, LoadingState, PageHeader } from "../components/common/ui";
import { formatDateTime } from "../lib/format";

const UNSAFE_EXAMPLE =
  "Hi Sam, our bank details changed. Please wire the payment to IBAN DE00 1234 5678 instead of using the PayPal invoice.";
const SAFE_EXAMPLE = "Hi Sam, a friendly reminder that invoice CIQ-01 for 450.00 USD is due today. Thank you!";

export function SafetyPage() {
  const report = useSafetyReport();

  return (
    <div>
      <PageHeader
        title="Safety & trust"
        description={
          report.data
            ? `Guardrails enforced in code, with live evidence from the audit trail · updated ${formatDateTime(report.data.generated_at)}`
            : "Guardrails enforced in code, with live evidence from the audit trail"
        }
      />
      {report.isPending && <LoadingState label="Reading the audit trail…" />}
      {report.isError && <ErrorState message={errorMessage(report.error)} onRetry={() => report.refetch()} />}
      {report.data && <SafetyContent report={report.data} />}
    </div>
  );
}

function SafetyContent({ report }: { report: SafetyReport }) {
  const { counts } = report;
  const clean = counts.executions_without_approval === 0;
  const evidence: { label: string; value: number; hint?: string }[] = [
    { label: "AI assistant requests", value: counts.agent_runs },
    { label: "Autopilot runs", value: counts.autopilot_runs },
    { label: "AI tool calls", value: counts.tool_calls, hint: `${counts.tool_calls_rejected} rejected by the backend` },
    { label: "AI messages blocked", value: counts.ai_messages_blocked, hint: "Failed the message safety check" },
    { label: "Actions proposed", value: counts.proposals },
    { label: "Approved by you", value: counts.approved_by_user },
    { label: "Approved by your policy", value: counts.approved_by_policy },
    { label: "Rejected by you", value: counts.rejected_by_user },
    {
      label: "Executed in PayPal",
      value: counts.executions_succeeded,
      hint: `${counts.executions_blocked} blocked before execution`,
    },
    { label: "Verified in PayPal", value: counts.verified_in_paypal },
  ];

  return (
    <div className="space-y-6">
      <section
        className={`flex flex-wrap items-center gap-4 rounded-xl p-5 text-white shadow-sm ${clean ? "bg-navy" : "bg-danger"}`}
      >
        <div className="grid size-12 shrink-0 place-items-center rounded-full bg-white/10">
          {clean ? (
            <ShieldCheck className="size-6 text-accent" aria-hidden />
          ) : (
            <CircleX className="size-6" aria-hidden />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-white/70">PayPal writes without an approval</p>
          <p className="text-3xl font-semibold tabular-nums">{counts.executions_without_approval}</p>
        </div>
        <p className="max-w-md text-sm text-white/80">
          {clean
            ? "Every PayPal write was approved by you or by a policy you turned on, executed once and verified in PayPal."
            : "Investigate now: an execution without a recorded approval was found in the audit trail."}
        </p>
      </section>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {evidence.map((item) => (
          <div key={item.label} className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <dt className="text-xs text-muted">{item.label}</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums text-ink">{item.value}</dd>
            {item.hint && <dd className="mt-0.5 text-xs text-muted">{item.hint}</dd>}
          </div>
        ))}
      </dl>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle title="Guardrails" subtitle="Enforced by the backend, not by the AI" />
          <ul className="divide-y divide-slate-100">
            {report.guardrails.map((guardrail) => (
              <li key={guardrail.name} className="flex gap-3 px-5 py-3">
                <Lock className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                <div>
                  <p className="text-sm font-medium text-ink">{guardrail.name}</p>
                  <p className="text-xs text-muted">{guardrail.description}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardTitle title="Message safety check" subtitle="Runs on every AI-written client message before you see it" />
          <div className="px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Blocks messages that</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
              {report.message_rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
            <MessageTester />
          </div>
        </Card>
      </div>
    </div>
  );
}

function MessageTester() {
  const [text, setText] = useState(UNSAFE_EXAMPLE);
  const check = useCheckMessage();

  function load(example: string) {
    setText(example);
    check.reset();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (text.trim()) check.mutate(text);
  }

  return (
    <form onSubmit={handleSubmit} className="mt-5 border-t border-slate-100 pt-4">
      <label htmlFor="safety-test" className="text-sm font-medium text-ink">
        Try it
      </label>
      <p className="text-xs text-muted">Paste any message, for example one a manipulated AI might write.</p>
      <textarea
        id="safety-test"
        rows={3}
        maxLength={2000}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          check.reset();
        }}
        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      />
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={check.isPending || !text.trim()}
          className="rounded-lg bg-brand px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-brand/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-50"
        >
          Check message
        </button>
        <button type="button" onClick={() => load(UNSAFE_EXAMPLE)} className="text-xs font-medium text-brand hover:underline">
          Unsafe example
        </button>
        <button type="button" onClick={() => load(SAFE_EXAMPLE)} className="text-xs font-medium text-brand hover:underline">
          Safe example
        </button>
      </div>

      <div aria-live="polite">
        {check.isError && <p className="mt-3 text-sm text-danger">{errorMessage(check.error)}</p>}
        {check.data &&
          (check.data.passed ? (
            <p className="mt-3 flex items-center gap-2 rounded-lg bg-success/10 px-3 py-2 text-sm text-success">
              <CircleCheck className="size-4" aria-hidden />
              Passed: safe to show for approval.
            </p>
          ) : (
            <div className="mt-3 rounded-lg bg-danger/5 px-3 py-2 text-sm text-danger">
              <p className="flex items-center gap-2 font-medium">
                <CircleX className="size-4" aria-hidden />
                Blocked before anyone could approve it
              </p>
              <ul className="mt-1 list-disc pl-6 text-xs">
                {check.data.violations.map((violation) => (
                  <li key={violation}>{violation}</li>
                ))}
              </ul>
            </div>
          ))}
      </div>
    </form>
  );
}
