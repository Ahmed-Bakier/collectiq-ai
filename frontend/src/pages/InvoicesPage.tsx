import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
  AllCommunityModule,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";
import { AgGridProvider, AgGridReact } from "ag-grid-react";
import { Download, Search, Sparkles } from "lucide-react";
import { errorMessage } from "../api/client";
import { useInvoiceAnalysis } from "../api/hooks";
import type { AnalyzedInvoice } from "../api/types";
import { ErrorState, LoadingState, PageHeader, PriorityBadge, StateBadge } from "../components/common/ui";
import { clientName, formatDate, formatMoney } from "../lib/format";

// AG Grid Community (MIT) with all community features.
const GRID_MODULES = [AllCommunityModule];

// AG Grid theme aligned with the CollectIQ design tokens.
const collectiqGridTheme = themeQuartz.withParams({
  accentColor: "#2563EB",
  fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  foregroundColor: "#172B4D",
  headerBackgroundColor: "#F8FAFC",
  headerTextColor: "#64748B",
  borderColor: "#E2E8F0",
  rowHoverColor: "#F1F5F9",
  wrapperBorderRadius: 12,
});

type FilterKey = "all" | "action" | "overdue" | "due_soon" | "draft" | "closed";

const FILTERS: { key: FilterKey; label: string; match: (item: AnalyzedInvoice) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "action", label: "Needs action", match: (item) => item.suggested_action !== "none" },
  { key: "overdue", label: "Overdue", match: (item) => item.collection_state === "overdue" },
  {
    key: "due_soon",
    label: "Due soon",
    match: (item) => item.collection_state === "due_soon" || item.collection_state === "due_today",
  },
  { key: "draft", label: "Drafts", match: (item) => item.collection_state === "draft" },
  { key: "closed", label: "Paid / closed", match: (item) => item.collection_state === "closed" },
];

function amountOwed(item: AnalyzedInvoice): string | null {
  return item.invoice.amount_due ?? item.invoice.total_amount;
}

function timingLabel(item: AnalyzedInvoice | undefined): string {
  if (!item) return "";
  if (item.days_overdue != null) return `${item.days_overdue}d overdue`;
  if (item.collection_state === "due_today") return "Due today";
  if (item.days_until_due != null && item.collection_state !== "closed") return `Due in ${item.days_until_due}d`;
  return "—";
}

function ClientCell({ data }: ICellRendererParams<AnalyzedInvoice>) {
  if (!data) return null;
  return (
    <div className="flex h-full flex-col justify-center leading-tight">
      <span className="font-medium text-ink">{clientName(data.invoice)}</span>
      {data.invoice.recipient_name && data.invoice.recipient_business_name && (
        <span className="text-xs text-muted">{data.invoice.recipient_name}</span>
      )}
    </div>
  );
}

function AskAgentCell({ data }: ICellRendererParams<AnalyzedInvoice>) {
  const navigate = useNavigate();
  if (!data || data.collection_state === "closed") return null;
  const label = data.invoice.invoice_number ?? data.invoice.id;
  const question = `Review invoice ${label} for ${clientName(data.invoice)} and propose the right action.`;
  return (
    <button
      type="button"
      onClick={() => navigate(`/assistant?q=${encodeURIComponent(question)}`)}
      className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-ink hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
    >
      <Sparkles className="size-3.5 text-accent" aria-hidden />
      Ask agent
    </button>
  );
}

export function InvoicesPage() {
  const analysis = useInvoiceAnalysis();
  const gridRef = useRef<AgGridReact<AnalyzedInvoice>>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");

  const allRows = useMemo(() => analysis.data?.invoices ?? [], [analysis.data]);
  const activeFilter = FILTERS.find((option) => option.key === filter) ?? FILTERS[0];
  const rows = useMemo(() => allRows.filter(activeFilter.match), [allRows, activeFilter]);

  const columnDefs = useMemo<ColDef<AnalyzedInvoice>[]>(
    () => [
      {
        headerName: "Client",
        colId: "client",
        valueGetter: (params) => (params.data ? clientName(params.data.invoice) : ""),
        cellRenderer: ClientCell,
        flex: 2,
        minWidth: 200,
      },
      { headerName: "Invoice #", field: "invoice.invoice_number", minWidth: 170 },
      {
        headerName: "Amount owed",
        colId: "amount",
        type: "rightAligned",
        filter: "agNumberColumnFilter",
        valueGetter: (params) => (params.data ? Number(amountOwed(params.data) ?? 0) : 0),
        valueFormatter: (params) =>
          params.data ? formatMoney(amountOwed(params.data), params.data.invoice.currency_code) : "",
        minWidth: 140,
      },
      {
        headerName: "Due date",
        field: "invoice.due_date",
        valueFormatter: (params) => formatDate(params.value as string | null),
        minWidth: 130,
      },
      { headerName: "Timing", colId: "timing", valueGetter: (params) => timingLabel(params.data), minWidth: 130 },
      {
        headerName: "State",
        field: "collection_state",
        cellRenderer: (params: ICellRendererParams<AnalyzedInvoice>) =>
          params.data ? <StateBadge state={params.data.collection_state} /> : null,
        minWidth: 130,
      },
      {
        headerName: "Priority",
        field: "priority_score",
        sort: "desc",
        filter: "agNumberColumnFilter",
        cellRenderer: (params: ICellRendererParams<AnalyzedInvoice>) =>
          params.data ? <PriorityBadge level={params.data.priority_level} score={params.data.priority_score} /> : null,
        minWidth: 150,
      },
      { headerName: "PayPal status", field: "invoice.status", minWidth: 130 },
      {
        headerName: "",
        colId: "ask",
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: AskAgentCell,
        minWidth: 130,
        maxWidth: 140,
      },
    ],
    [],
  );

  const defaultColDef = useMemo<ColDef<AnalyzedInvoice>>(
    () => ({ sortable: true, resizable: true, filter: true }),
    [],
  );

  return (
    <div>
      <PageHeader
        title="Invoices"
        description={
          analysis.data
            ? `Live from PayPal Sandbox · ${allRows.length} invoices · as of ${formatDate(analysis.data.as_of)}`
            : "Live from PayPal Sandbox"
        }
        actions={
          <button
            type="button"
            onClick={() => gridRef.current?.api.exportDataAsCsv({ fileName: "collectiq-invoices.csv" })}
            disabled={!analysis.data}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-ink hover:bg-slate-50 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <Download className="size-4" aria-hidden />
            Export CSV
          </button>
        }
      />

      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="group" aria-label="Filter invoices" className="flex flex-wrap gap-2">
          {FILTERS.map((option) => {
            const count = allRows.filter(option.match).length;
            const active = filter === option.key;
            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(option.key)}
                className={`rounded-full border px-3 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
                  active ? "border-navy bg-navy text-white" : "border-slate-200 bg-white text-ink hover:bg-slate-50"
                }`}
              >
                {option.label} <span className={active ? "text-white/70" : "text-muted"}>{count}</span>
              </button>
            );
          })}
        </div>
        <label className="relative block lg:w-72">
          <span className="sr-only">Search invoices</span>
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search client, invoice, status…"
            className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          />
        </label>
      </div>

      {analysis.isPending && <LoadingState label="Loading invoices from PayPal…" />}
      {analysis.isError && <ErrorState message={errorMessage(analysis.error)} onRetry={() => analysis.refetch()} />}
      {analysis.data && (
        <AgGridProvider modules={GRID_MODULES}>
          <AgGridReact<AnalyzedInvoice>
            ref={gridRef}
            theme={collectiqGridTheme}
            rowData={rows}
            columnDefs={columnDefs}
            defaultColDef={defaultColDef}
            quickFilterText={search}
            getRowId={(params) => params.data.invoice.id}
            rowHeight={52}
            domLayout="autoHeight"
            pagination
            paginationPageSize={20}
            paginationPageSizeSelector={[10, 20, 50]}
            overlayNoRowsTemplate="No invoices match these filters."
          />
        </AgGridProvider>
      )}
    </div>
  );
}
