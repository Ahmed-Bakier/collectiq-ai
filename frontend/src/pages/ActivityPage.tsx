import { useState } from "react";
import { errorMessage } from "../api/client";
import { useAuditEvents } from "../api/hooks";
import type { AuditEvent } from "../api/types";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/common/ui";
import { formatDateTime } from "../lib/format";

type ActorFilter = "all" | AuditEvent["actor"];

const ACTOR_STYLES: Record<AuditEvent["actor"], string> = {
  user: "bg-brand/10 text-brand ring-brand/20",
  agent: "bg-accent/10 text-accent ring-accent/20",
  system: "bg-slate-100 text-slate-600 ring-slate-200",
};

const EVENT_LABELS: Record<string, string> = {
  agent_run_requested: "Request received",
  agent_tool_call: "Tool call",
  action_proposed: "Action proposed",
  action_superseded: "Action superseded",
  action_revised: "Message revised",
  action_expired: "Approval expired",
  agent_run_completed: "Agent run completed",
  action_approved: "Approved",
  action_rejected: "Rejected",
  execution_started: "Execution started",
  execution_blocked: "Execution blocked",
  execution_succeeded: "Executed",
  execution_failed: "Execution failed",
  execution_outcome_unknown: "Outcome unknown",
  verification_completed: "Verified with PayPal",
  autopilot_run_completed: "Autopilot run",
  autopilot_settings_changed: "Autopilot settings changed",
  ai_output_blocked: "AI message blocked",
};

const EVENT_TONES: Record<string, string> = {
  execution_succeeded: "text-success",
  verification_completed: "text-success",
  execution_failed: "text-danger",
  execution_blocked: "text-danger",
  execution_outcome_unknown: "text-warning",
  action_approved: "text-brand",
  action_rejected: "text-muted",
};

export function ActivityPage() {
  const audit = useAuditEvents(200);
  const [actor, setActor] = useState<ActorFilter>("all");
  const events = (audit.data?.items ?? []).filter((event) => actor === "all" || event.actor === actor);

  return (
    <div>
      <PageHeader
        title="Activity Log"
        description="Append-only audit trail: what the agent proposed, what you decided and what PayPal confirmed."
        actions={
          <label className="flex items-center gap-2 text-sm text-muted">
            Actor
            <select
              value={actor}
              onChange={(event) => setActor(event.target.value as ActorFilter)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              <option value="all">All</option>
              <option value="user">User</option>
              <option value="agent">Agent</option>
              <option value="system">System</option>
            </select>
          </label>
        }
      />

      {audit.isPending && <LoadingState label="Loading activity…" />}
      {audit.isError && <ErrorState message={errorMessage(audit.error)} onRetry={() => audit.refetch()} />}
      {audit.data && (
        <Card className="overflow-hidden">
          {events.length === 0 ? (
            <EmptyState title="No activity yet" description="Agent runs, approvals and executions appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Time</th>
                    <th scope="col" className="px-4 py-3 font-medium">Actor</th>
                    <th scope="col" className="px-4 py-3 font-medium">Event</th>
                    <th scope="col" className="px-4 py-3 font-medium">Details</th>
                    <th scope="col" className="px-4 py-3 font-medium">Invoice</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {events.map((event) => (
                    <tr key={event.id} className="align-top">
                      <td className="whitespace-nowrap px-4 py-3 text-xs tabular-nums text-muted">
                        {formatDateTime(event.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-inset ${ACTOR_STYLES[event.actor]}`}
                        >
                          {event.actor}
                        </span>
                      </td>
                      <td className={`whitespace-nowrap px-4 py-3 font-medium ${EVENT_TONES[event.event_type] ?? "text-ink"}`}>
                        {EVENT_LABELS[event.event_type] ?? event.event_type}
                      </td>
                      <td className="px-4 py-3 text-ink">{event.message}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted">
                        {event.invoice_id ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
