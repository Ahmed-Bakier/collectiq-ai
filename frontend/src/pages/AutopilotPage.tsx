import { useState } from "react";
import { BadgeCheck, Bot, Play, ShieldCheck, SkipForward, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { useAutopilotSettings, useRunAutopilot, useUpdateAutopilotSettings } from "../api/hooks";
import type { AutopilotProposal, AutopilotRunResponse, AutopilotSettings, AutopilotTone } from "../api/types";
import { ActionCardById } from "../components/approvals/ActionCard";
import { LoadingState } from "../components/common/ui";

const PANEL = "rounded-xl border border-black/5 bg-white p-5 shadow-sm";

const TONE_STYLES: Record<AutopilotTone, { label: string; className: string }> = {
  friendly: { label: "Friendly", className: "bg-success/10 text-success" },
  firm: { label: "Firm", className: "bg-warning/15 text-amber-700" },
  final_notice: { label: "Final notice", className: "bg-danger/10 text-danger" },
};

export function AutopilotPage() {
  const settingsQuery = useAutopilotSettings();
  const run = useRunAutopilot();

  if (settingsQuery.isPending) return <LoadingState label="Loading autopilot…" />;
  if (settingsQuery.isError) return <ErrorBox message={errorMessage(settingsQuery.error)} />;
  const settings = settingsQuery.data;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-ink">
            <Bot className="size-6 text-accent" aria-hidden />
            Collection Autopilot
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            A deterministic playbook decides which invoices need action and how firm to be. AI writes the message.
            Nothing reaches PayPal without an approval: yours, or a strict policy you turn on.
          </p>
        </div>
        <button
          type="button"
          onClick={() => run.mutate()}
          disabled={!settings.enabled || run.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="size-4" aria-hidden />
          {run.isPending ? "Running playbook…" : "Run now"}
        </button>
      </header>

      {!settings.enabled && (
        <p role="status" className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-amber-800">
          Autopilot is paused. Turn it on to run the collection playbook.
        </p>
      )}
      {run.isError && <ErrorBox message={errorMessage(run.error)} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <ControlsPanel settings={settings} />
        <PlaybookPanel settings={settings} />
      </div>

      {run.data && <RunResults result={run.data} />}
    </div>
  );
}

// ---------- Controls ----------

function ControlsPanel({ settings }: { settings: AutopilotSettings }) {
  const update = useUpdateAutopilotSettings();
  const schedule =
    settings.schedule_interval_minutes > 0 ? `Every ${settings.schedule_interval_minutes} min` : "Manual (Run now)";
  const lastRun = settings.last_run_at ? new Date(settings.last_run_at).toLocaleString() : "Never";

  return (
    <section className={PANEL} aria-labelledby="autopilot-controls">
      <h2 id="autopilot-controls" className="font-semibold text-ink">
        Controls
      </h2>
      <div className="mt-2 divide-y divide-black/5">
        <ToggleRow
          label="Autopilot"
          description="Kill switch. When off, every run is refused."
          checked={settings.enabled}
          disabled={update.isPending}
          onChange={(enabled) => update.mutate({ enabled })}
        />
        <ToggleRow
          label="Auto-approve small friendly reminders"
          description={`Only friendly reminders up to the limit below, max ${settings.max_auto_actions_per_run} per run. Invoices, firm reminders and final notices always wait for you.`}
          checked={settings.auto_approve_enabled}
          disabled={update.isPending}
          onChange={(autoApprove) => update.mutate({ auto_approve_enabled: autoApprove })}
        />
        <AmountForm
          key={settings.auto_approve_max_amount}
          initial={settings.auto_approve_max_amount}
          disabled={update.isPending}
          onSave={(amount) => update.mutate({ auto_approve_max_amount: amount })}
        />
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <Detail label="Reminder cooldown" value={`${settings.cooldown_days} days`} />
        <Detail label="Schedule" value={schedule} />
        <Detail label="Last run" value={lastRun} />
      </dl>

      {update.isError && (
        <div className="mt-4">
          <ErrorBox message={errorMessage(update.error)} />
        </div>
      )}
    </section>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="mt-0.5 text-xs text-muted">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-50 ${
          checked ? "bg-accent" : "bg-black/20"
        }`}
      >
        <span
          aria-hidden
          className={`inline-block size-5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

function AmountForm({
  initial,
  disabled,
  onSave,
}: {
  initial: string;
  disabled: boolean;
  onSave: (amount: string) => void;
}) {
  const [value, setValue] = useState(initial);
  const amount = Number(value);
  const valid = value.trim() !== "" && Number.isFinite(amount) && amount >= 0 && amount <= 10000;
  const changed = valid && amount.toFixed(2) !== Number(initial).toFixed(2);

  return (
    <form
      className="flex flex-wrap items-end justify-between gap-3 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (changed) onSave(amount.toFixed(2));
      }}
    >
      <label className="text-sm">
        <span className="block font-medium text-ink">Auto-approve limit (USD)</span>
        <span className="mt-0.5 block text-xs text-muted">Reminders above this amount always need your approval.</span>
        <input
          type="number"
          min={0}
          max={10000}
          step="0.01"
          inputMode="decimal"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={!valid}
          className="mt-2 w-36 rounded-lg border border-black/10 px-3 py-1.5 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        />
      </label>
      <button
        type="submit"
        disabled={disabled || !changed}
        className="rounded-lg border border-black/10 px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
      >
        Save limit
      </button>
      {!valid && <p className="w-full text-xs text-danger">Enter an amount between 0 and 10,000.</p>}
    </form>
  );
}

// ---------- Playbook ----------

function PlaybookPanel({ settings }: { settings: AutopilotSettings }) {
  const friendlyApproval = settings.auto_approve_enabled
    ? `Auto-approved up to $${settings.auto_approve_max_amount}`
    : "Needs your approval";

  const steps: { when: string; action: string; tone?: AutopilotTone; approval: string }[] = [
    { when: "Invoice is still a draft", action: "Send invoice", approval: "Always needs your approval" },
    { when: "Due today – 7 days overdue", action: "Reminder", tone: "friendly", approval: friendlyApproval },
    { when: "8 – 21 days overdue", action: "Reminder", tone: "firm", approval: "Always needs your approval" },
    { when: "Over 21 days overdue", action: "Reminder", tone: "final_notice", approval: "Always needs your approval" },
  ];

  return (
    <section className={PANEL} aria-labelledby="autopilot-playbook">
      <h2 id="autopilot-playbook" className="font-semibold text-ink">
        Escalation playbook
      </h2>
      <ol className="mt-3 space-y-2">
        {steps.map((step, index) => (
          <li key={step.when} className="flex items-start gap-3 rounded-lg bg-surface px-3 py-2.5">
            <span
              aria-hidden
              className="grid size-6 shrink-0 place-items-center rounded-full bg-navy text-xs font-semibold text-white"
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">{step.when}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>{step.action}</span>
                {step.tone && <ToneBadge tone={step.tone} />}
                <span aria-hidden>·</span>
                <span>{step.approval}</span>
              </p>
            </div>
          </li>
        ))}
      </ol>

      <h3 className="mt-5 flex items-center gap-2 text-sm font-semibold text-ink">
        <ShieldCheck className="size-4 text-accent" aria-hidden />
        Guardrails
      </h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted">
        <li>Skips invoices that already have a proposal waiting for approval.</li>
        <li>No reminder if one was sent in the last {settings.cooldown_days} days.</li>
        <li>AI writes messages from invoice facts only; templates are used if the AI is unavailable.</li>
        <li>PayPal status is re-checked before and verified after every execution.</li>
        <li>Every decision is recorded in the Activity Log.</li>
      </ul>
    </section>
  );
}

// ---------- Run results ----------

function RunResults({ result }: { result: AutopilotRunResponse }) {
  const waiting = result.proposals.filter((proposal) => !proposal.auto_approved);
  const autoExecuted = result.proposals.filter((proposal) => proposal.auto_approved);

  return (
    <section aria-labelledby="autopilot-results" className="space-y-6">
      <div className={PANEL}>
        <h2 id="autopilot-results" className="font-semibold text-ink">
          Run results
        </h2>
        <p className="mt-1 text-sm text-muted">{result.summary}</p>
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Evaluated" value={result.evaluated_invoices} />
          <Stat label="Eligible" value={result.eligible_invoices} />
          <Stat label="Awaiting you" value={waiting.length} />
          <Stat label="Auto-executed" value={autoExecuted.length} />
          <Stat label="Skipped" value={result.skipped.length} />
        </dl>
        {result.proposals.length > 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
            <Sparkles className="size-3.5 text-accent" aria-hidden />
            {result.llm_fallback_used
              ? "AI was unavailable for at least one message, so a template was used."
              : "Messages drafted by AI from invoice facts."}
          </p>
        )}
        {result.eligible_invoices === 0 && (
          <p className="mt-3 text-sm text-ink">Nothing needs action right now. All open invoices are on track.</p>
        )}
      </div>

      {waiting.length > 0 && <ProposalGroup title="Awaiting your approval" proposals={waiting} />}
      {autoExecuted.length > 0 && <ProposalGroup title="Auto-executed by policy" proposals={autoExecuted} />}

      {result.skipped.length > 0 && (
        <div className={PANEL}>
          <h3 className="flex items-center gap-2 font-semibold text-ink">
            <SkipForward className="size-4 text-muted" aria-hidden />
            Skipped
          </h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">Invoice</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Client</th>
                  <th scope="col" className="py-2 font-medium">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5">
                {result.skipped.map((skip) => (
                  <tr key={skip.invoice_id}>
                    <td className="whitespace-nowrap py-2 pr-4 font-mono text-xs text-ink">
                      {skip.invoice_number ?? skip.invoice_id}
                    </td>
                    <td className="py-2 pr-4 text-ink">{skip.client ?? "—"}</td>
                    <td className="py-2 text-muted">{skip.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

function ProposalGroup({ title, proposals }: { title: string; proposals: AutopilotProposal[] }) {
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-ink">{title}</h3>
      {proposals.map((proposal) => (
        <div key={proposal.action.id}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <ToneBadge tone={proposal.tone} />
            {proposal.auto_approved && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                <BadgeCheck className="size-3.5" aria-hidden />
                Auto-approved by policy
              </span>
            )}
          </div>
          <ActionCardById actionId={proposal.action.id} />
        </div>
      ))}
    </div>
  );
}

// ---------- Small pieces ----------

function ToneBadge({ tone }: { tone: AutopilotTone }) {
  const style = TONE_STYLES[tone];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}>{style.label}</span>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-surface px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-xl font-semibold text-ink">{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-lg border border-danger/20 bg-danger/5 px-4 py-3 text-sm text-danger">
      {message}
    </p>
  );
}
