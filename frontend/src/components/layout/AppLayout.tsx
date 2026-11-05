import { NavLink, Outlet } from "react-router";
import { Bot, FileText, History, LayoutDashboard, Plug, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { usePayPalStatus } from "../../api/hooks";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/invoices", label: "Invoices", icon: FileText },
  { to: "/assistant", label: "AI Assistant", icon: Sparkles },
  { to: "/autopilot", label: "Autopilot", icon: Bot },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/activity", label: "Activity Log", icon: History },
  { to: "/integrations", label: "Integrations", icon: Plug },
];

export function AppLayout() {
  return (
    <div className="min-h-screen bg-surface font-sans text-ink md:flex">
      <aside className="bg-navy text-white md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col">
        <div className="flex items-center gap-2.5 px-5 py-4 md:py-6">
          <div aria-hidden className="grid size-9 place-items-center rounded-lg bg-accent text-sm font-bold">
            CQ
          </div>
          <div>
            <p className="font-semibold leading-tight">CollectIQ AI</p>
            <p className="text-xs text-white/60">Invoice collection agent</p>
          </div>
        </div>

        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible md:pb-0">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  isActive ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>

        <ConnectionFooter />
      </aside>

      <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function ConnectionFooter() {
  const { data, isPending } = usePayPalStatus();
  const connected = data?.connected ?? false;
  const label = isPending ? "Checking PayPal…" : connected ? "PayPal connected" : "PayPal not connected";

  return (
    <div className="hidden border-t border-white/10 px-5 py-4 md:block">
      <div className="flex items-center gap-2 text-sm">
        <span
          aria-hidden
          className={`size-2 rounded-full ${isPending ? "bg-white/40" : connected ? "bg-success" : "bg-danger"}`}
        />
        <span role="status">{label}</span>
      </div>
      <span className="mt-2 inline-flex rounded-md bg-warning/20 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-amber-200">
        Sandbox
      </span>
    </div>
  );
}
