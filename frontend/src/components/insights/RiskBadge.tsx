import type { RiskLevel } from "../../api/types";

const BADGE = "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

const RISK_STYLES: Record<RiskLevel, { label: string; className: string }> = {
  high: { label: "High risk", className: "bg-danger/10 text-danger ring-danger/20" },
  medium: { label: "Medium risk", className: "bg-warning/10 text-warning ring-warning/25" },
  low: { label: "Low risk", className: "bg-success/10 text-success ring-success/20" },
  new: { label: "New client", className: "bg-slate-100 text-slate-600 ring-slate-200" },
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const style = RISK_STYLES[level];
  return <span className={`${BADGE} ${style.className}`}>{style.label}</span>;
}
