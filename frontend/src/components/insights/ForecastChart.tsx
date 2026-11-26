import type { CashFlowForecast } from "../../api/types";
import { formatMoney } from "../../lib/format";

const PLOT_HEIGHT = 168;

/** Round the axis maximum up to a clean 1 / 2 / 2.5 / 5 step. */
function niceMax(value: number): number {
  if (value <= 0) return 1000;
  const base = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => value <= candidate * base) ?? 10;
  return step * base;
}

function axisLabel(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
      notation: value >= 10_000 ? "compact" : "standard",
    }).format(value);
  } catch {
    return String(Math.round(value));
  }
}

function LegendKey({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`size-2.5 rounded-sm ${swatch}`} />
      {label}
    </span>
  );
}

/** Weekly stacked columns: expected (accent) and at-risk (warning). Display only, no money math. */
export function ForecastChart({ forecast }: { forecast: CashFlowForecast }) {
  const currency = forecast.currency_code ?? "USD";
  const bars = forecast.buckets.map((bucket) => {
    const expected = Number(bucket.expected_amount);
    const atRisk = Number(bucket.at_risk_amount);
    return { bucket, expected, atRisk, total: expected + atRisk };
  });
  const max = niceMax(Math.max(0, ...bars.map((bar) => bar.total)));
  const ticks = [max, max / 2, 0];
  const position = (value: number) => `${(1 - value / max) * 100}%`;

  return (
    <figure>
      <figcaption className="sr-only">
        Expected collections per week for the next {forecast.horizon_days} days
      </figcaption>
      <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <LegendKey swatch="bg-accent" label="Expected" />
        <LegendKey swatch="bg-warning" label="At risk (high-risk client or 21+ days overdue)" />
      </div>

      <div className="flex gap-2">
        <div aria-hidden className="relative w-14 shrink-0" style={{ height: PLOT_HEIGHT }}>
          {ticks.map((tick) => (
            <span
              key={tick}
              className="absolute right-0 -translate-y-1/2 text-[11px] tabular-nums text-muted"
              style={{ top: position(tick) }}
            >
              {axisLabel(tick, currency)}
            </span>
          ))}
        </div>

        <div className="relative flex-1">
          <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0" style={{ height: PLOT_HEIGHT }}>
            {ticks.map((tick) => (
              <div key={tick} className="absolute inset-x-0 border-t border-slate-200" style={{ top: position(tick) }} />
            ))}
          </div>

          <ul className="relative grid grid-cols-4">
            {bars.map(({ bucket, expected, atRisk, total }) => (
              <li
                key={bucket.label}
                tabIndex={0}
                aria-label={`${bucket.label}: ${formatMoney(bucket.expected_amount, currency)} expected, ${formatMoney(
                  bucket.at_risk_amount,
                  currency,
                )} at risk, ${bucket.invoice_count} invoice(s)`}
                className="group relative flex flex-col items-center rounded-md outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <div className="flex w-full items-end justify-center" style={{ height: PLOT_HEIGHT }}>
                  <div className="relative flex w-6 flex-col gap-[2px]" style={{ height: `${(total / max) * 100}%` }}>
                    <span className="absolute bottom-full left-1/2 mb-1 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium tabular-nums text-ink">
                      {axisLabel(total, currency)}
                    </span>
                    {atRisk > 0 && <div className="rounded-t-[4px] bg-warning" style={{ flexGrow: atRisk }} />}
                    {expected > 0 && (
                      <div className={`bg-accent ${atRisk > 0 ? "" : "rounded-t-[4px]"}`} style={{ flexGrow: expected }} />
                    )}
                  </div>
                </div>
                <span className="mt-2 text-center text-[11px] text-muted">{bucket.label}</span>

                <div
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden w-52 -translate-x-1/2 rounded-lg bg-navy px-3 py-2 text-xs text-white shadow-lg group-hover:block group-focus-visible:block"
                >
                  <p className="font-semibold">{bucket.label}</p>
                  <p className="mt-1 flex justify-between gap-3">
                    <span className="text-white/70">Expected</span>
                    <span className="tabular-nums">{formatMoney(bucket.expected_amount, currency)}</span>
                  </p>
                  <p className="flex justify-between gap-3">
                    <span className="text-white/70">At risk</span>
                    <span className="tabular-nums">{formatMoney(bucket.at_risk_amount, currency)}</span>
                  </p>
                  <p className="flex justify-between gap-3">
                    <span className="text-white/70">Invoices</span>
                    <span className="tabular-nums">{bucket.invoice_count}</span>
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-medium text-brand">View as table</summary>
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">Week</th>
              <th scope="col" className="py-1 pr-3 font-medium">Expected</th>
              <th scope="col" className="py-1 pr-3 font-medium">At risk</th>
              <th scope="col" className="py-1 font-medium">Invoices</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {forecast.buckets.map((bucket) => (
              <tr key={bucket.label}>
                <td className="py-1 pr-3 text-ink">{bucket.label}</td>
                <td className="py-1 pr-3 tabular-nums text-ink">{formatMoney(bucket.expected_amount, currency)}</td>
                <td className="py-1 pr-3 tabular-nums text-ink">{formatMoney(bucket.at_risk_amount, currency)}</td>
                <td className="py-1 tabular-nums text-ink">{bucket.invoice_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
