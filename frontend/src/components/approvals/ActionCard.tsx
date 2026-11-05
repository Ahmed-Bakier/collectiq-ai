import type { ReactNode } from "react";
import { BellRing, CircleAlert, CircleCheck, LoaderCircle, Send, ShieldCheck, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { useAction, useApproveAction, useExecuteAction, useRejectAction } from "../../api/hooks";
import type { ActionRecord } from "../../api/types";
import { formatDateTime, formatMoney } from "../../lib/format";
import { ErrorState, LoadingState } from "../common/ui";

const ACTION_TITLES: Record<ActionRecord["action_type"], string> = {
  send_invoice: "Send invoice via PayPal",
  send_reminder: "Send payment reminder via PayPal",
};

const LABEL = "text-xs font-medium uppercase tracking-wide text-muted";
const PRIMARY_BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";
const SECONDARY_BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-ink hover:bg-slate-50 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

const TONES = {
  warning: "bg-warning/10 text-warning ring-warning/25",
  brand: "bg-brand/10 text-brand ring-brand/20",
  success: "bg-success/10 text-success ring-success/20",
  danger: "bg-danger/10 text-danger ring-danger/20",
  muted: "bg-slate-100 text-slate-600 ring-slate-200",
} as const;

function statusInfo(action: ActionRecord): { label: string; tone: keyof typeof TONES } {
  if (action.approval_status === "pending") return { label: "Awaiting your approval", tone: "warning" };
  if (action.approval_status === "rejected") return { label: "Rejected", tone: "muted" };
  if (action.approval_status === "expired") return { label: "Expired", tone: "muted" };
  if (action.approval_status === "superseded") return { label: "Superseded", tone: "muted" };
  if (action.execution_status === "not_started") return { label: "Approved · ready to execute", tone: "brand" };
  if (action.execution_status === "executing") return { label: "Executing…", tone: "brand" };
  if (action.execution_status === "failed") return { label: "Failed", tone: "danger" };
  if (action.execution_status === "outcome_unknown") return { label: "Outcome unknown", tone: "warning" };
  if (action.verification_status === "verified") return { label: "Executed · verified in PayPal", tone: "success" };
  if (action.verification_status === "mismatch") return { label: "Executed · verification mismatch", tone: "warning" };
  return { label: "Executed · not verified", tone: "warning" };
}

export function ActionCard({ action }: { action: ActionRecord }) {
  const approve = useApproveAction();
  const reject = useRejectAction();
  const execute = useExecuteAction();

  const busy = approve.isPending || reject.isPending || execute.isPending;
  const mutationError = approve.error ?? reject.error ?? execute.error;
  const isPending = action.approval_status === "pending";
  const canExecute = action.approval_status === "approved" && action.execution_status === "not_started";
  const status = statusInfo(action);
  const Icon = action.action_type === "send_invoice" ? Send : BellRing;

  return (
    <article
      aria-label={`${ACTION_TITLES[action.action_type]} for ${action.client_name ?? action.invoice_id}`}
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-start gap-3">
          <div aria-hidden className="grid size-9 place-items-center rounded-lg bg-brand/10 text-brand">
            <Icon className="size-4" />
          </div>
          <div>
            <p className="text-sm font-semibold text-ink">{ACTION_TITLES[action.action_type]}</p>
            <p className="text-xs text-muted">
              {action.client_name ?? "Unknown client"} · {action.invoice_number ?? action.invoice_id} ·{" "}
              {formatMoney(action.amount, action.currency_code)}
            </p>
          </div>
        </div>
        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[status.tone]}`}>
          {status.label}
        </span>
      </header>

      <div className="space-y-4 px-5 py-4 text-sm">
        <div>
          <p className={LABEL}>Why the agent proposes this</p>
          <p className="mt-1 text-ink">{action.reason}</p>
        </div>

        {action.message_to_client && (
          <div>
            <p className={LABEL}>Message to client</p>
            <blockquote className="mt-1 rounded-lg border-l-2 border-accent bg-slate-50 px-3 py-2 text-ink">
              {action.message_to_client}
            </blockquote>
          </div>
        )}

        <details className="rounded-lg border border-slate-200 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-muted">Exact PayPal parameters</summary>
          <pre className="mt-2 overflow-x-auto text-xs text-ink">{JSON.stringify(action.parameters, null, 2)}</pre>
          <p className="mt-2 text-xs text-muted">
            Approval is bound to parameter fingerprint <code>{action.parameters_hash.slice(0, 12)}…</code>. Any
            change requires a new approval.
          </p>
        </details>

        <Outcome action={action} />

        {mutationError && (
          <p role="alert" className="flex items-start gap-2 rounded-lg bg-danger/5 p-3 text-xs text-danger">
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {errorMessage(mutationError)}
          </p>
        )}
      </div>

      {(isPending || canExecute) && (
        <footer className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3">
          {isPending && (
            <>
              <button
                type="button"
                className={PRIMARY_BUTTON}
                disabled={busy}
                onClick={() => approve.mutate({ id: action.id, parametersHash: action.parameters_hash })}
              >
                {approve.isPending ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <ShieldCheck className="size-4" aria-hidden />}
                Approve
              </button>
              <button type="button" className={SECONDARY_BUTTON} disabled={busy} onClick={() => reject.mutate({ id: action.id })}>
                <X className="size-4" aria-hidden />
                Reject
              </button>
              <p className="text-xs text-muted">Nothing is sent to PayPal until you approve and execute.</p>
            </>
          )}
          {canExecute && (
            <>
              <button type="button" className={PRIMARY_BUTTON} disabled={busy} onClick={() => execute.mutate(action.id)}>
                {execute.isPending ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
                {execute.isPending ? "Executing in PayPal…" : "Execute in PayPal"}
              </button>
              <p className="text-xs text-muted">
                Approved {formatDateTime(action.decided_at)} · execute within 15 minutes.
              </p>
            </>
          )}
        </footer>
      )}
    </article>
  );
}

function Outcome({ action }: { action: ActionRecord }) {
  if (action.execution_status === "succeeded") {
    const verified = action.verification_status === "verified";
    return (
      <Panel tone="success" icon={<CircleCheck className="size-4" aria-hidden />} title={verified ? "Done — verified in PayPal" : "PayPal accepted the request"}>
        {verified
          ? "CollectIQ read the invoice back from PayPal after executing and confirmed the result."
          : "CollectIQ could not confirm the expected status when reading the invoice back from PayPal."}
        <span className="mt-1 block text-xs opacity-80">
          Executed {formatDateTime(action.executed_at)} · {action.external_reference}
        </span>
      </Panel>
    );
  }
  if (action.execution_status === "failed" || action.execution_status === "outcome_unknown") {
    const failed = action.execution_status === "failed";
    return (
      <Panel
        tone={failed ? "danger" : "warning"}
        icon={<CircleAlert className="size-4" aria-hidden />}
        title={failed ? "Not executed" : "Outcome unknown — not retried automatically"}
      >
        {action.failure_reason}
      </Panel>
    );
  }
  if (action.approval_status === "rejected") {
    return <Panel tone="muted" title="Rejected">You rejected this action. Nothing was sent to PayPal.</Panel>;
  }
  if (action.approval_status === "expired" || action.approval_status === "superseded") {
    return (
      <Panel tone="muted" title={action.approval_status === "expired" ? "Expired" : "Superseded"}>
        This proposal can no longer be approved. Ask the agent for a fresh analysis.
      </Panel>
    );
  }
  return null;
}

const PANEL_TONES = {
  success: "border-success/20 bg-success/5 text-success",
  danger: "border-danger/20 bg-danger/5 text-danger",
  warning: "border-warning/25 bg-warning/5 text-warning",
  muted: "border-slate-200 bg-slate-50 text-slate-600",
} as const;

function Panel({
  tone,
  title,
  icon,
  children,
}: {
  tone: keyof typeof PANEL_TONES;
  title: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div role="status" className={`flex items-start gap-2 rounded-lg border p-3 ${PANEL_TONES[tone]}`}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-sm opacity-90">{children}</p>
      </div>
    </div>
  );
}

export function ActionCardById({ actionId }: { actionId: string }) {
  const action = useAction(actionId);
  if (action.isPending) return <LoadingState label="Loading proposed action…" />;
  if (action.isError) return <ErrorState message={errorMessage(action.error)} />;
  return <ActionCard action={action.data} />;
}
