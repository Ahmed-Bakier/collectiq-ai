import type { ReactNode } from "react";
import { CircleAlert, Inbox, LoaderCircle } from "lucide-react";
import type { CollectionState, PriorityLevel } from "../../api/types";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>{children}</section>;
}

export function CardTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions}
    </header>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 p-6 text-sm text-muted">
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-danger/20 bg-danger/5 p-4 text-sm text-danger">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">Something went wrong</p>
        <p className="mt-0.5 text-danger/80">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-danger/30 px-3 py-1 text-xs font-medium hover:bg-danger/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/40"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <Inbox className="size-6 text-slate-300" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && <p className="max-w-sm text-xs text-muted">{description}</p>}
    </div>
  );
}

const BADGE = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

const STATE_STYLES: Record<CollectionState, { label: string; className: string }> = {
  overdue: { label: "Overdue", className: "bg-danger/10 text-danger ring-danger/20" },
  due_today: { label: "Due today", className: "bg-warning/10 text-warning ring-warning/25" },
  due_soon: { label: "Due soon", className: "bg-warning/10 text-warning ring-warning/25" },
  not_due: { label: "Not due", className: "bg-slate-100 text-slate-600 ring-slate-200" },
  no_due_date: { label: "No due date", className: "bg-slate-100 text-slate-600 ring-slate-200" },
  draft: { label: "Draft", className: "bg-brand/10 text-brand ring-brand/20" },
  pending: { label: "Payment pending", className: "bg-slate-100 text-slate-600 ring-slate-200" },
  closed: { label: "Closed", className: "bg-success/10 text-success ring-success/20" },
  unknown: { label: "Needs review", className: "bg-slate-100 text-slate-600 ring-slate-200" },
};

export function StateBadge({ state }: { state: CollectionState }) {
  const style = STATE_STYLES[state];
  return <span className={`${BADGE} ${style.className}`}>{style.label}</span>;
}

const PRIORITY_STYLES: Record<PriorityLevel, string> = {
  high: "bg-danger/10 text-danger ring-danger/20",
  medium: "bg-warning/10 text-warning ring-warning/25",
  low: "bg-slate-100 text-slate-600 ring-slate-200",
  none: "bg-slate-50 text-slate-400 ring-slate-200",
};

export function PriorityBadge({ level, score }: { level: PriorityLevel; score: number }) {
  return (
    <span className={`${BADGE} ${PRIORITY_STYLES[level]}`} title={`Priority score ${score}/100`}>
      {level === "none" ? "No priority" : `${level[0].toUpperCase()}${level.slice(1)} priority`}
    </span>
  );
}

export function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span
      className={`${BADGE} gap-1.5 ${
        connected ? "bg-success/10 text-success ring-success/20" : "bg-danger/10 text-danger ring-danger/20"
      }`}
    >
      <span aria-hidden className={`size-1.5 rounded-full ${connected ? "bg-success" : "bg-danger"}`} />
      {connected ? "Connected" : "Not connected"}
    </span>
  );
}
