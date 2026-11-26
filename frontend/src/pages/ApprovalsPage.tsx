import { useState } from "react";
import { Link } from "react-router";
import { errorMessage } from "../api/client";
import { useActions } from "../api/hooks";
import type { ApprovalStatus } from "../api/types";
import { ActionCard } from "../components/approvals/ActionCard";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/common/ui";

type Filter = ApprovalStatus | "all";

const FILTERS: { label: string; value: Filter }[] = [
  { label: "Awaiting approval", value: "pending" },
  { label: "Approved", value: "approved" },
  { label: "All recent", value: "all" },
];

export function ApprovalsPage() {
  const [filter, setFilter] = useState<Filter>("pending");
  const actions = useActions(filter === "all" ? undefined : filter);

  return (
    <div>
      <PageHeader
        title="Approvals"
        description="Every PayPal action proposed by the agent waits here for your decision. The backend enforces each rule."
      />

      <div role="group" aria-label="Filter actions" className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
              filter === option.value ? "bg-navy text-white" : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {actions.isPending && <LoadingState label="Loading actions…" />}
      {actions.isError && <ErrorState message={errorMessage(actions.error)} onRetry={() => actions.refetch()} />}
      {actions.data &&
        (actions.data.items.length === 0 ? (
          <Card>
            <EmptyState
              title="No actions here"
              description="Ask the AI Assistant to analyze your invoices. Its proposals appear here for approval."
            />
            <div className="pb-6 text-center">
              <Link to="/assistant" className="text-sm font-medium text-brand hover:underline">
                Open AI Assistant
              </Link>
            </div>
          </Card>
        ) : (
          <div className="space-y-4">
            {actions.data.items.map((action) => (
              <ActionCard key={action.id} action={action} />
            ))}
          </div>
        ))}
    </div>
  );
}
