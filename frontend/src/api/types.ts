// Types mirroring the FastAPI response models (backend/app/schemas).

export type CollectionState =
  | "overdue"
  | "due_today"
  | "due_soon"
  | "not_due"
  | "no_due_date"
  | "draft"
  | "pending"
  | "closed"
  | "unknown";

export type PriorityLevel = "high" | "medium" | "low" | "none";

export type SuggestedAction = "send_reminder" | "send_invoice" | "monitor" | "review" | "none";

export interface InvoiceSummary {
  id: string;
  invoice_number: string | null;
  status: string;
  recipient_name: string | null;
  recipient_business_name: string | null;
  recipient_email: string | null;
  currency_code: string | null;
  total_amount: string | null; // Decimal serialized as string
  amount_due: string | null;
  invoice_date: string | null; // YYYY-MM-DD
  due_date: string | null;
  payment_term: string | null;
}

export interface AnalyzedInvoice {
  invoice: InvoiceSummary;
  collection_state: CollectionState;
  days_overdue: number | null;
  days_until_due: number | null;
  priority_score: number;
  priority_level: PriorityLevel;
  suggested_action: SuggestedAction;
  reasons: string[];
}

export interface CurrencyTotals {
  currency_code: string;
  outstanding_amount: string;
  overdue_amount: string;
  draft_amount: string;
}

export interface AnalysisSummary {
  total_invoices: number;
  open_count: number;
  overdue_count: number;
  due_soon_count: number;
  draft_count: number;
  needs_review_count: number;
  totals_by_currency: CurrencyTotals[];
}

export interface InvoiceAnalysisResponse {
  as_of: string;
  timezone: string;
  due_soon_window_days: number;
  summary: AnalysisSummary;
  invoices: AnalyzedInvoice[];
}

export interface PayPalStatus {
  environment: string;
  credentials_configured: boolean;
  connected: boolean;
  app_id: string | null;
  checked_at: string;
  error: string | null;
}

export type ProposedActionType = "send_invoice" | "send_reminder";

export interface ProposedAction {
  id: string;
  action_type: ProposedActionType;
  invoice_id: string;
  invoice_number: string | null;
  client_name: string | null;
  amount: string | null;
  currency_code: string | null;
  reason: string;
  message_to_client: string | null;
  parameters: Record<string, unknown>;
  requires_approval: boolean;
  status: "awaiting_approval";
}

export interface ToolCallRecord {
  name: string;
  arguments: Record<string, unknown>;
  status: "ok" | "error";
  detail: string;
}

export interface AgentRunResponse {
  run_id: string;
  model: string;
  summary: string;
  status: "awaiting_approval" | "completed" | "incomplete";
  requires_approval: boolean;
  findings: AnalyzedInvoice[];
  proposed_actions: ProposedAction[];
  tool_calls: ToolCallRecord[];
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | "superseded";
export type ExecutionStatus = "not_started" | "executing" | "succeeded" | "failed" | "outcome_unknown";
export type VerificationStatus = "not_verified" | "verified" | "mismatch";

export interface ActionRecord {
  id: string;
  run_id: string;
  action_type: ProposedActionType;
  invoice_id: string;
  invoice_number: string | null;
  client_name: string | null;
  amount: string | null;
  currency_code: string | null;
  reason: string;
  message_to_client: string | null;
  parameters: Record<string, unknown>;
  parameters_hash: string;
  approval_status: ApprovalStatus;
  execution_status: ExecutionStatus;
  verification_status: VerificationStatus;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
  executed_at: string | null;
  external_reference: string | null;
  failure_reason: string | null;
}

export interface AuditEvent {
  id: number;
  created_at: string;
  event_type: string;
  actor: "user" | "agent" | "system";
  run_id: string | null;
  action_id: string | null;
  invoice_id: string | null;
  message: string;
  details: Record<string, unknown>;
}

// ---------- Collection Autopilot ----------

export type AutopilotTone = "friendly" | "firm" | "final_notice";

export interface AutopilotSettings {
  enabled: boolean;
  auto_approve_enabled: boolean;
  auto_approve_max_amount: string; // Decimal serialized as string
  cooldown_days: number;
  max_auto_actions_per_run: number;
  schedule_interval_minutes: number;
  last_run_at: string | null;
}

export interface AutopilotSettingsUpdate {
  enabled?: boolean;
  auto_approve_enabled?: boolean;
  auto_approve_max_amount?: string;
}

export interface SkippedInvoice {
  invoice_id: string;
  invoice_number: string | null;
  client: string | null;
  reason: string;
}

export interface AutopilotProposal {
  action: ActionRecord;
  tone: AutopilotTone;
  auto_approved: boolean;
  client_risk: RiskLevel | null;
}

export interface AutopilotRunResponse {
  run_id: string;
  trigger: string;
  summary: string;
  evaluated_invoices: number;
  eligible_invoices: number;
  auto_executed_count: number;
  llm_fallback_used: boolean;
  proposals: AutopilotProposal[];
  skipped: SkippedInvoice[];
}

// ---------- Client payment intelligence ----------

export type RiskLevel = "low" | "medium" | "high" | "new";

export interface ClientInsight {
  client: string;
  currency_code: string | null;
  invoice_count: number;
  paid_count: number;
  on_time_count: number;
  on_time_rate: number | null; // 0..1
  avg_days_late: number | null;
  max_days_late: number | null;
  open_count: number;
  open_amount: string;
  overdue_amount: string;
  oldest_overdue_days: number | null;
  risk_level: RiskLevel;
  risk_reasons: string[];
}

export interface ForecastBucket {
  label: string;
  start: string;
  end: string;
  expected_amount: string;
  at_risk_amount: string;
  invoice_count: number;
}

export interface ForecastInvoice {
  invoice_id: string;
  invoice_number: string | null;
  client: string;
  amount: string;
  due_date: string;
  expected_date: string;
  risk_level: RiskLevel;
  at_risk: boolean;
}

export interface CashFlowForecast {
  currency_code: string | null;
  horizon_days: number;
  total_open: string;
  expected_within_horizon: string;
  expected_later: string;
  at_risk_amount: string;
  unscheduled_amount: string;
  buckets: ForecastBucket[];
  invoices: ForecastInvoice[];
  method: string;
}

export interface InsightsResponse {
  as_of: string;
  timezone: string;
  clients: ClientInsight[];
  forecast: CashFlowForecast;
}

// ---------- Safety ----------

export interface SafetyCounts {
  agent_runs: number;
  autopilot_runs: number;
  tool_calls: number;
  tool_calls_rejected: number;
  ai_messages_blocked: number;
  proposals: number;
  approved_by_user: number;
  approved_by_policy: number;
  rejected_by_user: number;
  executions_succeeded: number;
  executions_blocked: number;
  verified_in_paypal: number;
  executions_without_approval: number;
}

export interface Guardrail {
  name: string;
  description: string;
}

export interface SafetyReport {
  generated_at: string;
  counts: SafetyCounts;
  guardrails: Guardrail[];
  message_rules: string[];
}

export interface MessageCheckResult {
  passed: boolean;
  violations: string[];
}

// ---------- Payment links ----------

export interface PaymentLinkResponse {
  invoice_id: string;
  invoice_number: string | null;
  client: string;
  status: string;
  amount_due: string | null;
  currency_code: string | null;
  pay_url: string;
  qr_svg_data_uri: string;
}
